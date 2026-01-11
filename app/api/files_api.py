# app/api/files_api.py
import uuid
import shutil
import magic
import base64
import json
import logging
from pathlib import Path
from PIL import Image
from typing import List, Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import crud_files, sql_session, crud_settings
from app.schemas import file_schemas

# --- MODIFICATION: Import du nouveau manager ---
from app.core.llm_manager import call_llm, LLMConfig, LLMProvider

logger = logging.getLogger(__name__)

# Define the base path for storing uploaded files, as mounted in docker-compose.yml
FILES_STORAGE_PATH = Path("/app/files")


# Main router for user-facing file operations
router = APIRouter(
    prefix="/files",
    tags=["Files API - User Facing"]
)

# New router specifically for bot/tool-facing operations
bot_router = APIRouter(
    prefix="/files",
    tags=["Files API - Bot/Tool Facing"]
)


def get_file_family(mime_type: str) -> str:
    """Determine a high-level file family from its MIME type."""
    if mime_type.startswith('image/'):
        return 'image'
    if mime_type.startswith('text/'):
        return 'text'
    if mime_type.startswith('audio/'):
        return 'audio'
    if mime_type.startswith('video/'):
        return 'video'
    if mime_type.startswith('application/pdf'):
        return 'document'
    if mime_type.startswith('application/') and ('zip' in mime_type or 'tar' in mime_type):
        return 'archive'
    return 'binary'

# --- Endpoints for Bot Tools (MCP Servers) ---

@bot_router.get("/bot/{bot_id}", response_model=List[file_schemas.File])
def list_files_for_bot(
    bot_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(sql_session.get_db)
):
    """
    Lists all available files for a given bot.
    This is a simplified endpoint for tool consumption.
    """
    files = crud_files.get_all_files_for_bot(db=db, bot_id=bot_id, limit=limit)
    return files

@bot_router.get("/search/bot/{bot_id}", response_model=List[file_schemas.File])
def search_files_for_bot(
    bot_id: int,
    query: str = Query(..., min_length=1, description="Search term for filename and description."),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(sql_session.get_db)
):
    """
    Searches files for a bot based on a query term.
    """
    files = crud_files.search_files_by_query_for_bot(db=db, bot_id=bot_id, query=query, limit=limit)
    return files

@bot_router.get("/{uuid}/bot/{bot_id}", response_model=file_schemas.FileDetails)
def get_file_details_for_bot(
    uuid: str,
    bot_id: int,
    db: Session = Depends(sql_session.get_db)
):
    """
    Gets detailed metadata for a specific file belonging to a bot.
    """
    db_file = crud_files.get_file_by_uuid_for_bot(db=db, uuid=uuid, bot_id=bot_id)
    if not db_file:
        raise HTTPException(status_code=404, detail=f"File with UUID {uuid} not found for this bot.")
    
    return file_schemas.FileDetails(
        uuid=db_file.uuid,
        filename=db_file.filename,
        file_type=db_file.file_type,
        size_bytes=db_file.file_size_bytes,
        analysis_content=db_file.description
    )

@bot_router.delete("/{uuid}/bot/{bot_id}", response_model=file_schemas.File)
def delete_file_for_bot(
    uuid: str,
    bot_id: int,
    db: Session = Depends(sql_session.get_db)
):
    """
    Permanently deletes a file (record and physical storage) for a bot.
    """
    db_file = crud_files.get_file_by_uuid_for_bot(db=db, uuid=uuid, bot_id=bot_id)
    if not db_file:
        raise HTTPException(status_code=404, detail=f"File with UUID {uuid} not found for this bot.")

    crud_files.delete_file_record_and_storage(db=db, db_file=db_file)
    
    return db_file


# --- Endpoints for User-Facing Operations (Untouched) ---

@router.post("/upload/bot/{bot_id}", response_model=file_schemas.File, status_code=status.HTTP_201_CREATED)
async def upload_file(
    bot_id: int,
    owner_discord_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(sql_session.get_db)
):
    """
    Uploads a file, saves it to persistent storage, and creates a record in the database.
    """
    file_uuid = str(uuid.uuid4())
    bot_storage_path = FILES_STORAGE_PATH / str(bot_id)
    bot_storage_path.mkdir(parents=True, exist_ok=True)
    
    storage_filename = f"{file_uuid}.dat"
    file_location = bot_storage_path / storage_filename

    try:
        file_content_chunk = await file.read(2048)
        await file.seek(0)

        mime_type = magic.from_buffer(file_content_chunk, mime=True)
        file_family = get_file_family(mime_type)
        file_size = file.size
        file_metadata = {}

        if file_family == 'image':
            try:
                img = Image.open(file.file)
                file_metadata['width'] = img.width
                file_metadata['height'] = img.height
                await file.seek(0)
            except Exception as e:
                print(f"Could not extract image metadata for {file.filename}: {e}")

        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not process or save file: {e}"
        )
    finally:
        await file.close()

    file_create_schema = file_schemas.FileCreate(
        uuid=file_uuid,
        bot_id=bot_id,
        owner_discord_id=owner_discord_id,
        filename=file.filename,
        file_type=mime_type,
        file_family=file_family,
        file_size_bytes=file_size,
        file_metadata=file_metadata,
        storage_path=str(file_location)
    )

    db_file = crud_files.create_file_record(db=db, file=file_create_schema)

    return db_file


@router.post("/{uuid}/describe-image", response_model=file_schemas.FileDescriptionResponse)
async def describe_image(
    uuid: str,
    requester_discord_id: str = Query(..., description="The Discord ID of the user requesting the description for access control."),
    db: Session = Depends(sql_session.get_db)
):
    """
    Generates a description for an image file using a multimodal LLM.
    """
    db_file = crud_files.get_accessible_file_by_uuid(db, uuid, requester_discord_id)

    if not db_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found or you do not have access.")
    
    if db_file.file_family != 'image':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This operation is only supported for image files.")

    if db_file.description:
        return file_schemas.FileDescriptionResponse(
            uuid=db_file.uuid,
            description=db_file.description,
            is_from_cache=True
        )

    settings = crud_settings.get_global_settings(db)
    # Pour l'instant, on utilise le serveur décisionnel comme proxy pour le serveur multimodal
    # Idéalement, il faudrait un champ spécifique 'multimodal_llm_server_url' dans les settings
    llm_server_url = settings.decisional_llm_server_url
    multimodal_model = settings.multimodal_llm_model

    if not llm_server_url:
         # Fallback default local
        llm_server_url = "http://host.docker.internal:11434"

    if not multimodal_model:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Multimodal LLM model is not configured in global settings.")

    try:
        with open(db_file.storage_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not read image file: {e}")

    # Construction de la configuration pour l'appel LLM
    # On suppose que le serveur multimodal est compatible Ollama pour l'instant
    # (car l'injection d'images est très spécifique selon les providers)
    llm_config = LLMConfig(
        server_url=llm_server_url,
        model_name=multimodal_model,
        context_window=2048, # Petit contexte suffisant pour une description
        provider=LLMProvider.AUTO, # Laisser le manager détecter
        api_key=settings.decisional_llm_api_key
    )

    # Note: L'envoi d'image n'est pas standardisé dans LiteLLM de manière aussi simple que Ollama
    # Pour l'instant, le LLM Manager tel que codé supporte mal les images génériques.
    # On va faire une tentative best-effort en construisant le message avec le champ 'images' style Ollama.
    # Si le provider détecté est Ollama, ça marchera.
    
    messages = [
        {
            "role": "user", 
            "content": "Describe this image in detail.", 
            "images": [encoded_image]
        }
    ]
    
    try:
        full_description = await call_llm(
            config=llm_config,
            system_prompt="You are an AI assistant capable of analyzing images.",
            messages=messages
        )

        if not full_description:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="LLM returned an empty description.")

    except Exception as e:
        logger.error(f"Error calling Multimodal LLM: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred with the LLM call: {e}")

    updated_file = crud_files.update_file_description(db, db_file, full_description)

    return file_schemas.FileDescriptionResponse(
        uuid=updated_file.uuid,
        description=updated_file.description,
        is_from_cache=False
    )


@router.post("/{uuid}/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze_file(
    uuid: str,
    background_tasks: BackgroundTasks,
    requester_discord_id: str = Query(..., description="The Discord ID of the user requesting the analysis for access control."),
    db: Session = Depends(sql_session.get_db)
):
    """
    Triggers a background task to analyze a file's content and generate a description.
    """
    db_file = crud_files.get_file_by_uuid(db, uuid)

    if not db_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    if db_file.owner_discord_id != requester_discord_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to analyze this file.")

    # --- MODIFICATION 3: Désactiver temporairement la fonctionnalité ---
    # La fonction cible dans crud_files a été supprimée. Nous désactivons cet endpoint
    # en attendant de réimplémenter la logique dans un module `file_analyzer`.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="File analysis is temporarily disabled during application refactoring."
    )

    # L'ancienne ligne, conservée pour référence :
    # background_tasks.add_task(crud_files.analyze_and_update_file_description, db, uuid)

    # return {"message": "File analysis has been scheduled."}


@router.get("/search/bot/{bot_id}", response_model=List[file_schemas.File])
def search_bot_files(
    bot_id: int,
    requester_discord_id: str = Query(..., description="The Discord ID of the user performing the search."),
    filename: Optional[str] = Query(None, description="Part of the filename to search for (case-insensitive)."),
    file_family: Optional[str] = Query(None, description="Filter by file family (e.g., 'image', 'text')."),
    owner_id: Optional[str] = Query(None, description="Filter by the Discord ID of the file owner."),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results to return."),
    db: Session = Depends(sql_session.get_db)
):
    """
    Searches for files associated with a specific bot, with access control.
    """
    files = crud_files.search_files(
        db=db,
        bot_id=bot_id,
        requester_discord_id=requester_discord_id,
        filename=filename,
        file_family=file_family,
        owner_id=owner_id,
        limit=limit
    )
    return files


@router.get("/admin/bot/{bot_id}", response_model=List[file_schemas.File])
def get_bot_files_for_admin(
    bot_id: int,
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(sql_session.get_db)
):
    """
    [Admin] Retrieves all files for a bot, bypassing access control.
    """
    files = crud_files.get_all_files_for_bot_admin(db=db, bot_id=bot_id, limit=limit)
    return files


@router.delete("/{uuid}", response_model=file_schemas.File)
def delete_file(uuid: str, db: Session = Depends(sql_session.get_db)):
    """
    [Admin] Soft-deletes a file record.
    """
    deleted_file = crud_files.delete_file_record(db=db, uuid=uuid)
    if not deleted_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with UUID {uuid} not found."
        )
    return deleted_file

router.include_router(bot_router)