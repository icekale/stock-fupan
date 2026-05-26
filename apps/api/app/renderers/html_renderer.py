from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.schemas.report import ReportDTO


_TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(enabled_extensions=("html", "j2")),
)


def render_mobile_report_html(
    report: ReportDTO,
    brand_name: str = "",
    brand_footer: str = "",
    disclaimer_enabled: bool = True,
) -> str:
    template = _env.get_template("mobile_report.html.j2")
    return template.render(
        report=report,
        brand_name=brand_name,
        brand_footer=brand_footer,
        disclaimer_enabled=disclaimer_enabled,
    )
