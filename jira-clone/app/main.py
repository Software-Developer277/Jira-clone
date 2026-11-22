from quart import Quart, jsonify

from .db import init_db
from .routers import auth_routes, issues, projects, workspaces

app = Quart(__name__, static_folder="static", static_url_path="")
app.json.sort_keys = False


@app.before_serving
async def startup():
    await init_db()


for module in (auth_routes, workspaces, projects, issues):
    app.register_blueprint(module.bp)


@app.get("/api/health")
async def health():
    return jsonify(ok=True)


@app.route("/")
async def index():
    return await app.send_static_file("index.html")


if __name__ == "__main__":
    import asyncio

    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    config = Config()
    config.bind = ["127.0.0.1:5000"]
    asyncio.run(serve(app, config))
