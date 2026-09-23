from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import settings
from app import db
from app.api.routes import router, current_user
from pathlib import Path

app = FastAPI(
    title=settings.app_name,
    version="1.0.0"
)

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static"
)

templates = Jinja2Templates(
    directory=Path(__file__).parent / "templates"
)

app.include_router(router)


def render(request, page, **ctx):
    return templates.TemplateResponse(request, page, ctx)


@app.on_event("startup")
def startup():
    db.init_db()

    from app.services.security import hash_password

    if not db.get_user(settings.admin_username):
        db.upsert_user(
            settings.admin_username,
            hash_password(settings.admin_password)
        )

    # Seed only metadata templates, never sample input data.
    if not db.list_templates():
        db.save_template(
            "Customer Shipment",
            "NIQ shipment target structure",
            [
                "Country",
                "Region",
                "Channel",
                "City/State",
                "Category",
                "Brand",
                "SKU",
                "Fact"
            ],
            {
                "period": "keep_as_columns",
                "traceability": True
            }
        )

        db.save_template(
            "Vendor Shipment",
            "Vendor shipment target structure",
            [
                "Country",
                "Region",
                "Channel",
                "City/State",
                "Category",
                "Brand",
                "SKU",
                "Fact"
            ],
            {
                "period": "keep_as_columns",
                "traceability": True
            }
        )

        db.save_template(
            "Employee",
            "Generic employee structure",
            [
                "Country",
                "Region",
                "Channel",
                "City/State",
                "Category",
                "Brand",
                "SKU",
                "Fact"
            ],
            {}
        )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "login.html")


def protected(request, page):
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)

    return render(request, page)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return protected(request, "index.html")


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    return protected(request, "upload.html")


@app.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    return protected(request, "history.html")


@app.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request):
    return protected(request, "analytics.html")


@app.get("/templates", response_class=HTMLResponse)
def templates_page(request: Request):
    return protected(request, "templates.html")