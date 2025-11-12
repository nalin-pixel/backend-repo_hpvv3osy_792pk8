import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Spotify-lite API running"}

# Database helpers
from database import db, create_document, get_documents

# Schemas
from schemas import Track, Playlist

# Utility to convert ObjectId to str

def serialize_doc(doc):
    if not doc:
        return doc
    doc = {**doc}
    if doc.get("_id"):
        doc["id"] = str(doc.pop("_id"))
    # Convert nested ObjectIds if any
    for k, v in list(doc.items()):
        if isinstance(v, ObjectId):
            doc[k] = str(v)
    return doc

# Seed some demo tracks if none exist
@app.post("/seed")
def seed():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    count = db["track"].count_documents({})
    if count > 0:
        return {"status": "ok", "seeded": False, "existing": count}

    demo_tracks = [
        {
            "title": "Dreamscape",
            "artist": "Nocturne",
            "album": "Midnight City",
            "cover_url": "https://images.unsplash.com/photo-1511379938547-c1f69419868d?w=800&q=80&auto=format&fit=crop",
            "audio_url": "https://cdn.pixabay.com/download/audio/2021/11/16/audio_7b2a3f9b9a.mp3?filename=lofi-study-112191.mp3",
            "duration_ms": 152000,
        },
        {
            "title": "Sunset Drive",
            "artist": "Neon Waves",
            "album": "Coastal Roads",
            "cover_url": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800&q=80&auto=format&fit=crop",
            "audio_url": "https://cdn.pixabay.com/download/audio/2021/12/07/audio_7b5b2f6d8b.mp3?filename=vibes-122242.mp3",
            "duration_ms": 180000,
        },
        {
            "title": "Crystal Air",
            "artist": "Aurora",
            "album": "Skylight",
            "cover_url": "https://images.unsplash.com/photo-1515263487990-61b07816b324?w=800&q=80&auto=format&fit=crop",
            "audio_url": "https://cdn.pixabay.com/download/audio/2022/03/15/audio_7e0b7b5d03.mp3?filename=chill-ambient-10962.mp3",
            "duration_ms": 210000,
        },
    ]

    for t in demo_tracks:
        create_document("track", t)

    return {"status": "ok", "seeded": True, "count": len(demo_tracks)}

# Tracks endpoints
@app.get("/tracks")
def list_tracks(limit: int = 50):
    try:
        docs = get_documents("track", {}, limit)
        return [serialize_doc(d) for d in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CreateTrack(BaseModel):
    title: str
    artist: str
    album: Optional[str] = None
    cover_url: Optional[str] = None
    audio_url: str
    duration_ms: Optional[int] = None

@app.post("/tracks")
def create_track(payload: CreateTrack):
    try:
        track = Track(**payload.model_dump())
        _id = create_document("track", track)
        doc = db["track"].find_one({"_id": ObjectId(_id)})
        return serialize_doc(doc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Playlists endpoints (very basic)
class CreatePlaylist(BaseModel):
    name: str
    description: Optional[str] = None
    cover_url: Optional[str] = None

@app.post("/playlists")
def create_playlist(payload: CreatePlaylist):
    try:
        pl = {**payload.model_dump(), "tracks": []}
        _id = create_document("playlist", pl)
        doc = db["playlist"].find_one({"_id": ObjectId(_id)})
        return serialize_doc(doc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/playlists")
def list_playlists(limit: int = 50):
    try:
        docs = get_documents("playlist", {}, limit)
        return [serialize_doc(d) for d in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class AddTrackPayload(BaseModel):
    track_id: str

@app.post("/playlists/{playlist_id}/tracks")
def add_track_to_playlist(playlist_id: str, payload: AddTrackPayload):
    try:
        pid = ObjectId(playlist_id)
        tid = ObjectId(payload.track_id) if ObjectId.is_valid(payload.track_id) else None
        if tid is None:
            # It might be a string id from our create_document return; attempt cast
            try:
                tid = ObjectId(payload.track_id)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid track id")

        db["playlist"].update_one({"_id": pid}, {"$addToSet": {"tracks": str(tid)}})
        doc = db["playlist"].find_one({"_id": pid})
        return serialize_doc(doc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Health + DB test route retained
@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
