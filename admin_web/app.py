import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import actions
import auth
import bus
import reports
import settings
import stats

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Hire Admin")

STATIC_DIR = Path(__file__).resolve().parent / "static"


class LoginBody(BaseModel):
    username: str
    password: str


class MessageBody(BaseModel):
    text: str


class SettingsBody(BaseModel):
    demo_mode: bool | None = None
    daily_amount: float | None = None


class EventBody(BaseModel):
    event: str
    data: dict = {}


@app.post("/api/login")
async def login(body: LoginBody):
    if body.username == settings.ADMIN_USER and body.password == settings.ADMIN_PASS:
        return {"ok": True, "token": auth.create_token()}
    raise HTTPException(status_code=401, detail="wrong login")


@app.get("/api/overview")
async def overview(_: str = Depends(auth.require_admin)):
    return stats.get_overview()


@app.get("/api/sales")
async def sales(days: int = 30, _: str = Depends(auth.require_admin)):
    return stats.get_sales(days)


@app.get("/api/clients")
async def clients(status: str | None = None, _: str = Depends(auth.require_admin)):
    return stats.get_clients(status)


@app.get("/api/settings")
async def get_settings(_: str = Depends(auth.require_admin)):
    return stats.get_settings()


@app.post("/api/settings")
async def post_settings(body: SettingsBody, _: str = Depends(auth.require_admin)):
    result = actions.save_settings(body.demo_mode, body.daily_amount)
    if result.get("ok"):
        await bus.bus.broadcast("settings_changed", {})
    return result


@app.post("/api/clients/{user_id}/approve")
async def approve(user_id: int, _: str = Depends(auth.require_admin)):
    result = await actions.approve(user_id)
    if result.get("ok"):
        await bus.bus.broadcast("client_updated", {"user_id": user_id, "status": "active"})
    return result


@app.post("/api/clients/{user_id}/reject")
async def reject(user_id: int, _: str = Depends(auth.require_admin)):
    result = await actions.reject(user_id)
    if result.get("ok"):
        await bus.bus.broadcast("client_updated", {"user_id": user_id, "status": "rejected"})
    return result


@app.post("/api/clients/{user_id}/revoke")
async def revoke(user_id: int, _: str = Depends(auth.require_admin)):
    result = await actions.revoke(user_id)
    if result.get("ok"):
        await bus.bus.broadcast("client_updated", {"user_id": user_id, "status": "expired"})
    return result


@app.post("/api/clients/{user_id}/extend")
async def extend(user_id: int, _: str = Depends(auth.require_admin)):
    result = await actions.extend(user_id)
    if result.get("ok"):
        await bus.bus.broadcast("client_updated", {"user_id": user_id})
    return result


@app.post("/api/clients/{user_id}/message")
async def message(user_id: int, body: MessageBody, _: str = Depends(auth.require_admin)):
    return await actions.message(user_id, body.text)


@app.post("/api/broadcast")
async def broadcast(body: MessageBody, _: str = Depends(auth.require_admin)):
    return await actions.broadcast(body.text)


@app.get("/api/report.xlsx")
async def report(_: str = Depends(auth.require_admin)):
    data, filename = reports.build_report()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/internal/event")
async def internal_event(body: EventBody, x_internal_token: str = Header(default="")):
    if not settings.INTERNAL_TOKEN or x_internal_token != settings.INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="forbidden")
    await bus.bus.broadcast(body.event, body.data)
    return {"ok": True}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    token = ws.query_params.get("token", "")
    if not auth.check_token(token):
        await ws.close(code=4401)
        return
    await ws.accept()
    await bus.bus.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await bus.bus.remove(ws)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
