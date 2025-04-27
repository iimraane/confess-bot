# keep_alive.py
import os
from aiohttp import web

async def ping(request):
    return web.Response(text="I'm alive!")

def run():
    app = web.Application()
    app.router.add_get("/", ping)      # route GET /
    web.run_app(app, port=int(os.environ.get("PORT", 8080)))
