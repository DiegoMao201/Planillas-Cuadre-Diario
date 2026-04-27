from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote
import hashlib
import html
import os
import re
import smtplib
import time
import unicodedata
from zoneinfo import ZoneInfo

import dropbox
import gspread
import pandas as pd
import streamlit as st
import yagmail
from dropbox.exceptions import ApiError
from oauth2client.service_account import ServiceAccountCredentials


APP_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = APP_DIR.parent
LOGO_PATH = APP_DIR / "LOGO FERREINOX SAS BIC 2024.png"
EMPLOYEE_MASTER_CANDIDATES = [
    APP_DIR / "base_datos_empleados.xlsx",
    APP_DIR / "data" / "base_datos_empleados.xlsx",
    WORKSPACE_DIR / "base_datos_empleados.xlsx",
]

MAIN_PAGE = "Planillas.py"
RECIBOS_PAGE = "pages/1_Recibos_de_Caja.py"
VIATICOS_PAGE = "pages/2_Viaticos.py"
SOLICITUD_PAGE = "pages/3_Solicitudes_de_Permisos.py"
GESTION_SOLICITUDES_PAGE = "pages/4_Gestion_de_Solicitudes.py"
MOTO_INSPECTION_PAGE = "pages/5_Inspeccion_Preoperacional_Motos.py"
DEFAULT_APPROVAL_URL = "https://planillas-cuadre-diario-contabilidad.streamlit.app/Solicitudes_de_Permisos"
COLOMBIA_TZ = ZoneInfo("America/Bogota")
GOOGLE_SHEETS_RETRY_ATTEMPTS = 4
GOOGLE_SHEETS_RETRY_BASE_SECONDS = 0.8
SOLICITUDES_READ_CACHE_TTL_SECONDS = 120
SOLICITUDES_REPORT_SYNC_COOLDOWN_SECONDS = 180

REQUEST_REASONS = [
    {
        "codigo": "1",
        "tipo": "Permiso",
        "nombre": "Cita medica, tratamiento medico o examen medico especializado",
    },
    {
        "codigo": "2",
        "tipo": "Permiso",
        "nombre": "Permiso voluntario para diligencias personales, familiares o similares",
    },
    {
        "codigo": "3",
        "tipo": "Licencia",
        "nombre": "Licencias obligatorias remuneradas por ley",
    },
    {
        "codigo": "4",
        "tipo": "Licencia",
        "nombre": "Licencia no remunerada",
    },
    {
        "codigo": "5",
        "tipo": "Vacaciones",
        "nombre": "Vacaciones",
    },
    {
        "codigo": "6",
        "tipo": "Permiso",
        "nombre": "Beneficio de cumpleanos / jornada de familia",
    },
    {
        "codigo": "7",
        "tipo": "Compensatorio",
        "nombre": "Compensatorio por dia trabajado",
    },
]

REQUEST_HEADERS = [
    "Solicitud_ID",
    "Fecha_Registro",
    "Fecha_Solicitud",
    "Estado",
    "Tipo_Solicitud",
    "Motivo_Codigo",
    "Motivo_Descripcion",
    "Cedula",
    "Numero_Empleado",
    "Apellido",
    "Nombre_Completo",
    "Cargo",
    "Sede",
    "Tipo_Contrato",
    "Fecha_Ingreso",
    "Correo_Empleado",
    "Telefono_Empleado",
    "Fecha_Inicial",
    "Fecha_Final",
    "Hora_Salida",
    "Tiempo_Total",
    "Persona_A_Cargo",
    "Cual_Licencia",
    "Fecha_Dia_Trabajado",
    "Detalle_Solicitud",
    "Autorizacion_Descuento",
    "Dias_Aprobados",
    "Periodo_Correspondiente",
    "Dias_Pendientes_Periodo",
    "Fecha_Reincorporacion",
    "Observaciones_RRHH",
    "Responsable_Revision",
    "Fecha_Respuesta",
    "Medio_Respuesta",
    "Correo_Enviado_A_RRHH",
    "Correo_Respuesta_Empleado",
    "Whatsapp_Listo",
    "Adjunto_Nombre",
    "Adjunto_URL",
    "Adjunto_Storage",
    "Adjunto_Estado",
    "Ultima_Actualizacion",
    "Fuente_Registro",
]

NOVEDADES_HEADERS = [
    "Novedad_ID",
    "Solicitud_ID",
    "Fecha_Evento",
    "Tipo_Evento",
    "Estado_Resultante",
    "Responsable",
    "Cedula",
    "Nombre_Completo",
    "Sede",
    "Tipo_Solicitud",
    "Resumen",
    "Canal",
]

AUDIT_HEADERS = [
    "Auditoria_ID",
    "Solicitud_ID",
    "Fecha_Evento",
    "Accion",
    "Responsable",
    "Detalle",
]

PARAMETERS_HEADERS = ["Tipo", "Codigo", "Nombre", "Descripcion", "Activo"]
REPORT_HEADERS = ["Seccion", "Dimension", "Valor", "Cantidad", "Porcentaje"]

MOTO_PROFILE_HEADERS = [
    "Cedula",
    "Tipo_Identificacion",
    "Numero_Identificacion",
    "Nombre_Conductor",
    "Numero_Identificacion_Conductor",
    "Cargo_Conductor",
    "Sede",
    "Placa_Motocicleta",
    "Fecha_Vencimiento_SOAT",
    "Fecha_Vencimiento_Tecnomecanica",
    "Ultima_Actualizacion",
]

MOTO_INSPECTION_HEADERS = [
    "Inspeccion_ID",
    "Fecha_Registro",
    "Fecha_Inspeccion",
    "Sede",
    "Responsable_Inspeccion",
    "Responsable_Inspeccion_Otro",
    "Tipo_Identificacion",
    "Numero_Identificacion",
    "Cedula",
    "Numero_Empleado",
    "Nombre_Conductor",
    "Numero_Identificacion_Conductor",
    "Cargo_Conductor",
    "Correo_Conductor",
    "Telefono_Conductor",
    "Placa_Motocicleta",
    "Medicamentos_Somnolencia",
    "Descanso_Minimo_6_Horas",
    "Alcohol_O_Sustancias",
    "Licencia_Vigente",
    "Fecha_Vencimiento_SOAT",
    "Porta_SOAT_Vigente",
    "Certificado_Tecnomecanica",
    "Fecha_Vencimiento_Tecnomecanica",
    "Tarjeta_Propiedad",
    "Herramientas",
    "Kilometraje_Actual",
    "Estado_Presencia_Fugas",
    "Estado_Nivel_Liquido_Frenos",
    "Estado_Nivel_Aceite_Combustible",
    "Estado_Suspension_Delantera",
    "Estado_Suspension_Trasera",
    "Estado_Freno_Delantero",
    "Estado_Freno_Trasero",
    "Estado_Presion_Aire_Llantas",
    "Estado_Llantas",
    "Estado_Profundidad_Labrado",
    "Estado_Luces_Direccionales_Delanteras",
    "Estado_Luces_Direccionales_Traseras",
    "Estado_Luces_Delanteras",
    "Estado_Luces_Traseras",
    "Estado_Pito",
    "Estado_Protector_Cadena",
    "Estado_Tablero",
    "Estado_Espejos",
    "Estado_Sistema_Carga",
    "Estado_Gato_Central_Lateral",
    "Estado_Casco",
    "Fallas_Plan_Accion",
    "Firma_Nombre",
    "Firma_URL",
    "Firma_Storage",
    "Firma_Estado",
    "Tratamiento_Datos",
    "Fuente_Registro",
]

DEFAULT_PARAMETER_ROWS = [
    ["ESTADO", "PENDIENTE", "Pendiente", "Solicitud creada por el empleado", "SI"],
    ["ESTADO", "APROBADA", "Aprobada", "Solicitud aprobada por talento humano", "SI"],
    ["ESTADO", "NEGADA", "Negada", "Solicitud negada por talento humano", "SI"],
    ["ESTADO", "EN_REVISION", "En revision", "Solicitud en gestion administrativa", "SI"],
    *[
        ["MOTIVO", item["codigo"], item["tipo"], item["nombre"], "SI"]
        for item in REQUEST_REASONS
    ],
]


def current_colombia_datetime() -> datetime:
    return datetime.now(COLOMBIA_TZ)


def current_colombia_date() -> date:
    return current_colombia_datetime().date()


def format_colombia_timestamp() -> str:
    return current_colombia_datetime().strftime("%d/%m/%Y %H:%M:%S")


def initialize_access_state() -> None:
    defaults = {
        "access_role": "guest",
        "authenticated": False,
        "last_access_error": "",
        "store_profile_key": "",
        "store_profile_label": "",
        "authorized_store": "",
        "authorized_series": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")
    return text.lower()


def _clean_digits(value: object) -> str:
    return re.sub(r"\D", "", "" if value is None else str(value))


def _clean_display_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _column_from_aliases(df: pd.DataFrame, aliases: list[str]) -> str:
    normalized = {_normalize_text(column): column for column in df.columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return ""


def current_role() -> str:
    initialize_access_state()
    return st.session_state.get("access_role", "guest")


def has_access(required_role: str) -> bool:
    role = current_role()
    if role == "admin":
        return True
    if required_role == "store":
        return role == "store"
    if required_role == "admin":
        return role == "admin"
    return required_role == "public"


def _coerce_secret_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def get_store_profiles() -> dict[str, dict[str, object]]:
    raw_profiles = st.secrets.get("store_profiles", {})
    if not hasattr(raw_profiles, "items"):
        return {}

    profiles: dict[str, dict[str, object]] = {}
    for profile_key, raw_profile in raw_profiles.items():
        profile_data = dict(raw_profile) if hasattr(raw_profile, "items") else {}
        store_name = str(profile_data.get("tienda") or profile_data.get("store") or "").strip()
        hashed_password = str(
            profile_data.get("hashed_password") or profile_data.get("password_hash") or ""
        ).strip()
        plain_password = str(
            profile_data.get("password") or profile_data.get("plain_password") or ""
        ).strip()
        profile_label = str(
            profile_data.get("label") or profile_data.get("nombre") or store_name or profile_key
        ).strip()
        allowed_series = _coerce_secret_string_list(
            profile_data.get("series") or profile_data.get("serie")
        )

        if (not store_name and not allowed_series) or (not hashed_password and not plain_password):
            continue

        profiles[str(profile_key)] = {
            "key": str(profile_key),
            "label": profile_label,
            "store": store_name,
            "hashed_password": hashed_password,
            "plain_password": plain_password,
            "series": allowed_series,
        }

    return profiles


def current_authorized_store() -> str:
    initialize_access_state()
    return str(st.session_state.get("authorized_store", "")).strip()


def current_authorized_series() -> list[str]:
    initialize_access_state()
    series = st.session_state.get("authorized_series", [])
    return _coerce_secret_string_list(series)


def is_store_profile_active() -> bool:
    return current_role() == "store" and bool(
        current_authorized_store() or current_authorized_series()
    )


def filter_stores_for_access(store_options: list[str]) -> list[str]:
    allowed_series = current_authorized_series()
    authorized_store = current_authorized_store()
    if not is_store_profile_active():
        return store_options

    if allowed_series:
        filtered_by_series = [
            store for store in store_options if str(store).strip() in allowed_series
        ]
        if filtered_by_series:
            return filtered_by_series
        return allowed_series

    if not authorized_store:
        return store_options

    filtered = [store for store in store_options if str(store).strip() == authorized_store]
    return filtered or [authorized_store]


def filter_series_for_access(series_options: list[str]) -> list[str]:
    allowed_series = current_authorized_series()
    if not is_store_profile_active() or not allowed_series:
        return series_options

    filtered = [series for series in series_options if str(series).strip() in allowed_series]
    return filtered or allowed_series


def get_receipt_series_options() -> list[str]:
    configured_series = _coerce_secret_string_list(st.secrets.get("receipt_series", []))
    if configured_series:
        return configured_series
    return ["189U", "157U", "156U"]


def _get_secret_hash(role: str) -> str:
    credentials = st.secrets.get("credentials", {})
    if role == "admin":
        return credentials.get("admin_hashed_password") or ""
    return ""


def login_with_password(role: str, password: str) -> tuple[bool, str]:
    if role != "admin":
        return False, "Ese tipo de acceso ya no esta habilitado. Use su perfil de tienda o la clave administrativa."

    expected_hash = _get_secret_hash(role)
    if not expected_hash:
        return False, f"No se encontro la clave configurada para el rol {role}."

    hashed_input = hashlib.sha256(password.encode()).hexdigest()
    if hashed_input != expected_hash:
        return False, "La clave ingresada es incorrecta."

    st.session_state["access_role"] = role
    st.session_state["authenticated"] = True
    st.session_state["last_access_error"] = ""
    st.session_state["store_profile_key"] = ""
    st.session_state["store_profile_label"] = ""
    st.session_state["authorized_store"] = ""
    st.session_state["authorized_series"] = []
    return True, ""


def login_store_profile(profile_key: str, password: str) -> tuple[bool, str]:
    profiles = get_store_profiles()
    profile = profiles.get(profile_key)
    if not profile:
        return False, "No se encontro el perfil de tienda configurado."

    hashed_input = hashlib.sha256(password.encode()).hexdigest()
    matches_hash = bool(profile.get("hashed_password")) and hashed_input == profile["hashed_password"]
    matches_plain = bool(profile.get("plain_password")) and password == profile["plain_password"]
    if not matches_hash and not matches_plain:
        return False, "La clave ingresada es incorrecta."

    allowed_series = _coerce_secret_string_list(profile.get("series"))
    authorized_store = "" if allowed_series else str(profile.get("store") or "").strip()

    st.session_state["access_role"] = "store"
    st.session_state["authenticated"] = True
    st.session_state["last_access_error"] = ""
    st.session_state["store_profile_key"] = profile["key"]
    st.session_state["store_profile_label"] = profile["label"]
    st.session_state["authorized_store"] = authorized_store
    st.session_state["authorized_series"] = allowed_series
    return True, ""


def logout() -> None:
    st.session_state["access_role"] = "guest"
    st.session_state["authenticated"] = False
    st.session_state["last_access_error"] = ""
    st.session_state["store_profile_key"] = ""
    st.session_state["store_profile_label"] = ""
    st.session_state["authorized_store"] = ""
    st.session_state["authorized_series"] = []


AUTH_SESSION_KEYS = [
    "authenticated",
    "access_role",
    "last_access_error",
    "store_profile_key",
    "store_profile_label",
    "authorized_store",
    "authorized_series",
]


def reset_session_state(*preserved_keys: str) -> None:
    keys_to_keep = set(AUTH_SESSION_KEYS)
    keys_to_keep.update(preserved_keys)

    for key in list(st.session_state.keys()):
        if key not in keys_to_keep:
            del st.session_state[key]

    initialize_access_state()


def render_brand_header(title: str, subtitle: str = "") -> None:
    header_cols = st.columns([1, 4])
    with header_cols[0]:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=120)
    with header_cols[1]:
        st.title(title)
        if subtitle:
            st.caption(subtitle)


def inject_shared_css() -> None:
    st.markdown(
        """
        <style>
        .ferreinox-card {
            border: 1px solid rgba(11, 57, 84, 0.12);
            border-radius: 18px;
            padding: 1.2rem 1.3rem;
            background: linear-gradient(180deg, #ffffff 0%, #f5f8fb 100%);
            box-shadow: 0 10px 30px rgba(11, 57, 84, 0.06);
        }
        .ferreinox-badge {
            display: inline-block;
            padding: 0.28rem 0.7rem;
            border-radius: 999px;
            background: #dceefb;
            color: #0b3954;
            font-size: 0.82rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }
        .ferreinox-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 0.8rem;
            margin-top: 0.9rem;
        }
        .ferreinox-field {
            padding: 0.75rem 0.9rem;
            border-radius: 14px;
            background: #ffffff;
            border: 1px solid rgba(11, 57, 84, 0.08);
        }
        .ferreinox-field label {
            display: block;
            font-size: 0.76rem;
            text-transform: uppercase;
            color: #557085;
            margin-bottom: 0.25rem;
            font-weight: 700;
        }
        .ferreinox-field span {
            color: #183b56;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def resolve_employee_master_path() -> Path:
    for candidate in EMPLOYEE_MASTER_CANDIDATES:
        if candidate.exists():
            return candidate
    searched_paths = ", ".join(str(path) for path in EMPLOYEE_MASTER_CANDIDATES)
    raise FileNotFoundError(
        f"No se encontro base_datos_empleados.xlsx. Rutas revisadas: {searched_paths}"
    )


def render_sidebar(active_label: str) -> None:
    initialize_access_state()
    store_profiles = get_store_profiles()
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=170)
        st.markdown("### Accesos")
        st.page_link(SOLICITUD_PAGE, label="Solicitud de permisos", icon="📝")
        st.page_link(MOTO_INSPECTION_PAGE, label="Inspeccion motos", icon="🏍️")

        if has_access("store"):
            st.markdown("### Mi tienda")
            st.page_link(MAIN_PAGE, label="Cuadre diario", icon="💵")
            st.page_link(RECIBOS_PAGE, label="Recibos de caja", icon="🧾")

        if has_access("admin"):
            st.markdown("### Administracion")
            st.page_link(VIATICOS_PAGE, label="Viaticos", icon="🚗")
            st.page_link(GESTION_SOLICITUDES_PAGE, label="Gestion de solicitudes", icon="📊")

        st.divider()
        st.caption(f"Vista actual: {active_label}")

        if current_role() == "guest":
            with st.expander("Ingresar con clave", expanded=False):
                if store_profiles:
                    profile_options = list(store_profiles.keys())
                    selected_profile_key = st.selectbox(
                        "Perfil de tienda",
                        options=profile_options,
                        format_func=lambda key: str(store_profiles[key]["label"]),
                        key="sidebar_store_profile_key",
                    )
                    with st.form("sidebar_login_store_profile"):
                        profile_password = st.text_input("Clave de la tienda", type="password")
                        profile_submit = st.form_submit_button(
                            "Entrar a mi tienda",
                            use_container_width=True,
                        )
                        if profile_submit:
                            ok, message = login_store_profile(selected_profile_key, profile_password)
                            if ok:
                                st.rerun()
                            st.error(message)

                with st.form("sidebar_login_admin"):
                    admin_password = st.text_input("Clave administracion", type="password")
                    admin_submit = st.form_submit_button("Entrar a reportes y aprobacion", use_container_width=True)
                    if admin_submit:
                        ok, message = login_with_password("admin", admin_password)
                        if ok:
                            st.rerun()
                        st.error(message)
        else:
            if current_role() == "admin":
                role_label = "Administrador"
            elif current_role() == "store":
                profile_label = st.session_state.get("store_profile_label") or current_authorized_store()
                role_label = f"Tienda: {profile_label}"
            st.success(f"Acceso activo: {role_label}")
            if st.button("Cerrar sesion", use_container_width=True):
                logout()
                st.rerun()


def require_access(required_role: str, page_title: str, description: str) -> None:
    initialize_access_state()
    if has_access(required_role):
        return

    store_profiles = get_store_profiles()

    inject_shared_css()
    render_brand_header(page_title, description)
    st.markdown(
        """
        <div class="ferreinox-card">
            <span class="ferreinox-badge">Acceso controlado</span>
            <p style="margin-top: 0.8rem; color: #183b56;">
                Este modulo requiere una clave valida. El formulario de solicitudes para empleados sigue abierto sin clave.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    if store_profiles:
        access_cols = st.columns([1.35, 1.15, 1.0])
    else:
        access_cols = st.columns([1.25, 1.1])

    current_col = 0
    if store_profiles:
        with access_cols[current_col]:
            st.markdown("#### Perfil por tienda")
            selected_profile_key = st.selectbox(
                "Perfil autorizado",
                options=list(store_profiles.keys()),
                format_func=lambda key: str(store_profiles[key]["label"]),
                key=f"portal_store_profile_{page_title}",
            )
            with st.form(f"portal_login_store_{page_title}"):
                password = st.text_input("Ingrese la clave de la tienda", type="password")
                submitted = st.form_submit_button("Habilitar mi tienda", use_container_width=True)
                if submitted:
                    ok, message = login_store_profile(selected_profile_key, password)
                    if ok:
                        st.rerun()
                    st.error(message)
        current_col += 1

    with access_cols[current_col]:
        st.markdown("#### Clave administrativa")
        with st.form(f"portal_login_admin_{page_title}"):
            password = st.text_input("Ingrese la clave administrativa", type="password")
            submitted = st.form_submit_button("Habilitar menu administrativo", use_container_width=True)
            if submitted:
                ok, message = login_with_password("admin", password)
                if ok:
                    st.rerun()
                st.error(message)

    with access_cols[current_col + 1]:
        st.markdown("#### Acceso empleados")
        st.page_link(SOLICITUD_PAGE, label="Abrir formulario de solicitud", icon="📝")
        st.caption("Este acceso se mantiene publico para que el empleado solo vea su formato.")

    st.stop()


@st.cache_data(ttl=900)
def load_employee_master() -> pd.DataFrame:
    employee_master_path = resolve_employee_master_path()
    df = pd.read_excel(employee_master_path, sheet_name="Base Empleados")
    df = df.loc[:, [column for column in df.columns if str(column).strip()]]

    column_map = {
        "fecha_ingreso": _column_from_aliases(df, ["fecha_de_ingreso"]),
        "anos_laborales": _column_from_aliases(df, ["anos_laborales"]),
        "numero_empleado": _column_from_aliases(df, ["n_de_empleado", "numero_de_empleado", "n_empleado"]),
        "apellido": _column_from_aliases(df, ["apellido"]),
        "nombre_completo": _column_from_aliases(df, ["nombre_completo"]),
        "fecha_nacimiento": _column_from_aliases(df, ["fecha_de_nacimiento"]),
        "edad": _column_from_aliases(df, ["edad"]),
        "cedula": _column_from_aliases(df, ["cedula"]),
        "ciudad_expedicion": _column_from_aliases(df, ["ciudad_de_expedicion"]),
        "genero": _column_from_aliases(df, ["genero"]),
        "sede": _column_from_aliases(df, ["sede"]),
        "cargo": _column_from_aliases(df, ["cargo"]),
        "tipo_contrato": _column_from_aliases(df, ["tipo_de_contrato"]),
        "correo": _column_from_aliases(df, ["correo_electronico"]),
        "direccion": _column_from_aliases(df, ["direccion"]),
        "telefono": _column_from_aliases(df, ["telefono"]),
    }

    cleaned = pd.DataFrame()
    for target, source in column_map.items():
        cleaned[target] = df[source].map(_clean_display_value) if source else ""

    cleaned["cedula_lookup"] = cleaned["cedula"].map(_clean_digits)
    cleaned = cleaned[cleaned["cedula_lookup"] != ""].copy()
    cleaned["telefono_whatsapp"] = cleaned["telefono"].map(build_whatsapp_number)
    cleaned["correo"] = cleaned["correo"].str.strip()
    cleaned.sort_values(by=["nombre_completo", "cedula_lookup"], inplace=True)
    cleaned.reset_index(drop=True, inplace=True)
    return cleaned


def find_employee_by_cedula(cedula: str) -> dict[str, str] | None:
    lookup_value = _clean_digits(cedula)
    if not lookup_value:
        return None

    employee_df = load_employee_master()
    matches = employee_df[employee_df["cedula_lookup"] == lookup_value]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


@st.cache_resource(ttl=600)
def connect_to_base_spreadsheet():
    creds_json = dict(st.secrets["google_credentials"])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    client = gspread.authorize(creds)
    spreadsheet_name = st.secrets["google_sheets"]["spreadsheet_name"]
    spreadsheet = client.open(spreadsheet_name)
    return spreadsheet


def _run_gspread_call(action: str, operation, *args, **kwargs):
    last_error: Exception | None = None
    for attempt in range(GOOGLE_SHEETS_RETRY_ATTEMPTS):
        try:
            return operation(*args, **kwargs)
        except gspread.exceptions.WorksheetNotFound:
            raise
        except Exception as error:
            last_error = error
            if attempt == GOOGLE_SHEETS_RETRY_ATTEMPTS - 1:
                break
            time.sleep(GOOGLE_SHEETS_RETRY_BASE_SECONDS * (2 ** attempt))

    raise RuntimeError(
        f"No fue posible {action} en Google Sheets tras varios intentos."
    ) from last_error


def _column_letter(column_number: int) -> str:
    result = ""
    current = max(1, int(column_number))
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_range(title: str, cell_range: str) -> str:
    return f"'{title.replace("'", "''")}'!{cell_range}"


def _worksheet_has_content(rows: list[list[object]]) -> bool:
    return any(any(str(cell).strip() for cell in row) for row in rows)


def _get_existing_worksheets(spreadsheet) -> dict[str, object]:
    worksheets = _run_gspread_call("listar hojas", spreadsheet.worksheets)
    return {worksheet.title: worksheet for worksheet in worksheets}


def _ensure_worksheet_exists(
    spreadsheet,
    existing_worksheets: dict[str, object],
    title: str,
    headers: list[str],
    rows: int = 2000,
):
    worksheet = existing_worksheets.get(title)
    if worksheet is not None:
        return worksheet

    worksheet = _run_gspread_call(
        f"crear la hoja {title}",
        spreadsheet.add_worksheet,
        title=title,
        rows=rows,
        cols=max(26, len(headers) + 5),
    )
    _run_gspread_call(
        f"escribir encabezados en {title}",
        worksheet.update,
        "A1",
        [headers],
    )
    existing_worksheets[title] = worksheet
    return worksheet


def _get_sheet_previews(spreadsheet, sheet_titles: list[str]) -> dict[str, list[list[str]]]:
    response = _run_gspread_call(
        "leer encabezados de solicitudes",
        spreadsheet.values_batch_get,
        [_sheet_range(title, "1:2") for title in sheet_titles],
    )
    value_ranges = response.get("valueRanges", []) if isinstance(response, dict) else []

    previews: dict[str, list[list[str]]] = {}
    for title, value_range in zip(sheet_titles, value_ranges):
        previews[title] = value_range.get("values", []) or []
    for title in sheet_titles:
        previews.setdefault(title, [])
    return previews


def _ensure_headers_for_sheets(
    worksheets: dict[str, object],
    previews: dict[str, list[list[str]]],
    sheet_specs: dict[str, list[str]],
) -> None:
    for title, headers in sheet_specs.items():
        preview_rows = previews.get(title, [])
        current_headers = preview_rows[0] if preview_rows else []
        has_data_rows = _worksheet_has_content(preview_rows[1:])
        if current_headers == headers:
            continue
        if (not current_headers or not _worksheet_has_content([current_headers])) and not has_data_rows:
            _run_gspread_call(
                f"asegurar encabezados en {title}",
                worksheets[title].update,
                "A1",
                [headers],
            )


def _ensure_sheet_bootstrap(worksheets: dict[str, object], previews: dict[str, list[list[str]]]) -> None:
    _ensure_headers_for_sheets(
        worksheets,
        previews,
        {
            "Solicitudes_Registros": REQUEST_HEADERS,
            "Solicitudes_Novedades": NOVEDADES_HEADERS,
            "Solicitudes_Auditoria": AUDIT_HEADERS,
            "Solicitudes_Parametros": PARAMETERS_HEADERS,
            "Solicitudes_Reporte_Gerencia": REPORT_HEADERS,
        },
    )

    parameter_rows = previews.get("Solicitudes_Parametros", [])
    if not _worksheet_has_content(parameter_rows[1:]):
        _run_gspread_call(
            "precargar parametros de solicitudes",
            worksheets["Solicitudes_Parametros"].append_rows,
            DEFAULT_PARAMETER_ROWS,
        )


@st.cache_resource(ttl=600)
def get_solicitudes_worksheets() -> dict[str, object]:
    spreadsheet = connect_to_base_spreadsheet()
    existing_worksheets = _get_existing_worksheets(spreadsheet)
    registros_ws = _ensure_worksheet_exists(spreadsheet, existing_worksheets, "Solicitudes_Registros", REQUEST_HEADERS, rows=5000)
    novedades_ws = _ensure_worksheet_exists(spreadsheet, existing_worksheets, "Solicitudes_Novedades", NOVEDADES_HEADERS, rows=5000)
    auditoria_ws = _ensure_worksheet_exists(spreadsheet, existing_worksheets, "Solicitudes_Auditoria", AUDIT_HEADERS, rows=5000)
    parametros_ws = _ensure_worksheet_exists(spreadsheet, existing_worksheets, "Solicitudes_Parametros", PARAMETERS_HEADERS, rows=200)
    reporte_ws = _ensure_worksheet_exists(spreadsheet, existing_worksheets, "Solicitudes_Reporte_Gerencia", REPORT_HEADERS, rows=3000)

    _ensure_sheet_bootstrap(
        {
            "Solicitudes_Registros": registros_ws,
            "Solicitudes_Novedades": novedades_ws,
            "Solicitudes_Auditoria": auditoria_ws,
            "Solicitudes_Parametros": parametros_ws,
            "Solicitudes_Reporte_Gerencia": reporte_ws,
        },
        _get_sheet_previews(
            spreadsheet,
            [
                "Solicitudes_Registros",
                "Solicitudes_Novedades",
                "Solicitudes_Auditoria",
                "Solicitudes_Parametros",
                "Solicitudes_Reporte_Gerencia",
            ],
        ),
    )

    return {
        "spreadsheet": spreadsheet,
        "registros": registros_ws,
        "novedades": novedades_ws,
        "auditoria": auditoria_ws,
        "parametros": parametros_ws,
        "reporte": reporte_ws,
    }


def _sheet_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "SI" if value else "NO"
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%Y")
    if pd.isna(value):
        return ""
    return str(value).strip()


def generate_inspection_id(prefix: str, cedula: str, plate: str = "") -> str:
    plate_suffix = _normalize_text(plate).upper()[:6]
    id_suffix = _clean_digits(cedula)[-4:] or "0000"
    timestamp = current_colombia_datetime().strftime("%Y%m%d%H%M%S")
    suffix = f"-{plate_suffix}" if plate_suffix else ""
    return f"{prefix}-{timestamp}-{id_suffix}{suffix}"


def generate_request_id(cedula: str) -> str:
    return f"SOL-{current_colombia_datetime().strftime('%Y%m%d%H%M%S')}-{_clean_digits(cedula)[-4:]}"


def get_reason_metadata(reason_code: str) -> dict[str, str]:
    for item in REQUEST_REASONS:
        if item["codigo"] == str(reason_code):
            return item
    return {"codigo": str(reason_code), "tipo": "Permiso", "nombre": "Solicitud"}


def build_whatsapp_number(phone_value: object) -> str:
    digits = _clean_digits(phone_value)
    if not digits:
        return ""
    if digits.startswith("57"):
        return digits
    if len(digits) == 10:
        return f"57{digits}"
    return digits


def build_whatsapp_url(record: dict[str, str]) -> str:
    phone_number = build_whatsapp_number(record.get("Telefono_Empleado", ""))
    if not phone_number:
        return ""

    message = build_whatsapp_message(record)
    return f"https://wa.me/{phone_number}?text={quote(message)}"


def build_whatsapp_message(record: dict[str, str]) -> str:
    employee = record.get("Nombre_Completo", "Empleado")
    request_id = record.get("Solicitud_ID", "")
    status = record.get("Estado", "Pendiente")
    request_type = record.get("Tipo_Solicitud", "Solicitud")
    reason = record.get("Motivo_Descripcion", "")
    start_date = record.get("Fecha_Inicial", "")
    end_date = record.get("Fecha_Final", "")
    hour = record.get("Hora_Salida", "")
    total_time = record.get("Tiempo_Total", "")
    approved_days = record.get("Dias_Aprobados", "")
    reincorporation = record.get("Fecha_Reincorporacion", "")
    observations = record.get("Observaciones_RRHH", "") or "Sin observaciones adicionales."
    responsible = record.get("Responsable_Revision", "Talento Humano") or "Talento Humano"

    period_text = ""
    if start_date and end_date and start_date != end_date:
        period_text = f"del {start_date} al {end_date}"
    else:
        period_text = start_date or end_date

    reason_lower = reason.lower()
    status_lower = status.lower()
    detail_lines: list[str] = []

    if request_type == "Vacaciones":
        if status == "Aprobada":
            detail_lines.append(f"Su solicitud de vacaciones fue aprobada para el periodo {period_text}.".strip())
            if approved_days:
                detail_lines.append(f"Dias aprobados: {approved_days}.")
            if reincorporation:
                detail_lines.append(f"Fecha de reincorporacion: {reincorporation}.")
        elif status == "Negada":
            detail_lines.append(f"Su solicitud de vacaciones para el periodo {period_text} no fue aprobada.".strip())
        else:
            detail_lines.append(f"Su solicitud de vacaciones se encuentra {status_lower}.".strip())
    elif "cita medica" in reason_lower or "medico" in reason_lower:
        schedule_text = period_text or "la fecha registrada"
        if hour:
            schedule_text = f"{schedule_text} a las {hour}".strip()
        if total_time:
            schedule_text = f"{schedule_text} con un tiempo estimado de {total_time}".strip()
        if status == "Aprobada":
            detail_lines.append(f"Fue autorizado su permiso por cita medica para {schedule_text}.".strip())
        elif status == "Negada":
            detail_lines.append(f"No fue autorizado su permiso por cita medica solicitado para {schedule_text}.".strip())
        else:
            detail_lines.append(f"Su permiso por cita medica se encuentra {status_lower}.".strip())
    else:
        subject_text = f"su {request_type.lower()}" if request_type else "su solicitud"
        if status == "Aprobada":
            detail_lines.append(f"Fue aprobada {subject_text} {period_text and f'para {period_text}' or ''}.".replace("  ", " ").strip())
        elif status == "Negada":
            detail_lines.append(f"No fue aprobada {subject_text} {period_text and f'para {period_text}' or ''}.".replace("  ", " ").strip())
        else:
            detail_lines.append(f"{subject_text.capitalize()} se encuentra {status_lower}.".strip())
        if reason:
            detail_lines.append(f"Motivo registrado: {reason}.")
        if total_time and request_type != "Vacaciones":
            detail_lines.append(f"Tiempo solicitado: {total_time}.")

    detail_lines.append(f"Solicitud: {request_id}.")
    detail_lines.append(f"Observaciones de Talento Humano: {observations}")
    detail_lines.append(f"Gestionado por: {responsible}.")
    detail_lines.append("Si requiere aclaraciones, por favor comuniquese con Talento Humano.")

    return "\n".join([f"Hola {employee}.", "", *detail_lines])


def _approval_review_url() -> str:
    links = st.secrets.get("app_links", {})
    return links.get("permissions_review_url", DEFAULT_APPROVAL_URL)


def invalidate_solicitudes_cache() -> None:
    load_solicitudes_management_data.clear()
    st.session_state["solicitudes_report_needs_sync"] = True
    st.session_state.pop("solicitudes_report_signature", None)
    st.session_state.pop("solicitudes_report_synced_at", None)


def append_request_record(worksheet, record: dict[str, object]) -> None:
    _run_gspread_call(
        "registrar solicitud",
        worksheet.append_row,
        [_sheet_value(record.get(header, "")) for header in REQUEST_HEADERS],
    )
    invalidate_solicitudes_cache()


def update_request_record(worksheet, request_id: str, record: dict[str, object]) -> None:
    cell = _run_gspread_call(
        f"ubicar la solicitud {request_id}",
        worksheet.find,
        request_id,
        in_column=1,
    )
    _run_gspread_call(
        f"actualizar la solicitud {request_id}",
        worksheet.update,
        f"A{cell.row}",
        [[_sheet_value(record.get(header, "")) for header in REQUEST_HEADERS]],
    )
    invalidate_solicitudes_cache()


def append_novedad(worksheet, record: dict[str, str], event_type: str, summary: str, channel: str, responsible: str) -> None:
    row = [
        f"NOV-{current_colombia_datetime().strftime('%Y%m%d%H%M%S%f')}",
        record.get("Solicitud_ID", ""),
        format_colombia_timestamp(),
        event_type,
        record.get("Estado", ""),
        responsible,
        record.get("Cedula", ""),
        record.get("Nombre_Completo", ""),
        record.get("Sede", ""),
        record.get("Tipo_Solicitud", ""),
        summary,
        channel,
    ]
    _run_gspread_call("registrar novedad", worksheet.append_row, row)
    invalidate_solicitudes_cache()


def append_audit_log(worksheet, request_id: str, action: str, responsible: str, detail: str) -> None:
    row = [
        f"AUD-{current_colombia_datetime().strftime('%Y%m%d%H%M%S%f')}",
        request_id,
        format_colombia_timestamp(),
        action,
        responsible,
        detail,
    ]
    _run_gspread_call("registrar auditoria", worksheet.append_row, row)
    invalidate_solicitudes_cache()


def _rows_to_dataframe(values: list[list[str]], expected_headers: list[str]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame(columns=expected_headers)

    source_headers = [str(value).strip() for value in values[0]]
    if not _worksheet_has_content([source_headers]):
        return pd.DataFrame(columns=expected_headers)

    normalized_rows: list[list[str]] = []
    header_count = len(source_headers)
    for row in values[1:]:
        normalized = [str(value).strip() for value in row[:header_count]]
        if len(normalized) < header_count:
            normalized.extend([""] * (header_count - len(normalized)))
        if _worksheet_has_content([normalized]):
            normalized_rows.append(normalized)

    if not normalized_rows:
        return pd.DataFrame(columns=expected_headers)

    df = pd.DataFrame(normalized_rows, columns=source_headers)
    for header in expected_headers:
        if header not in df.columns:
            df[header] = ""
    return df[expected_headers].copy()


@st.cache_data(ttl=SOLICITUDES_READ_CACHE_TTL_SECONDS, show_spinner=False)
def load_solicitudes_management_data() -> dict[str, pd.DataFrame]:
    worksheets = get_solicitudes_worksheets()
    spreadsheet = worksheets["spreadsheet"]
    response = _run_gspread_call(
        "leer datos administrativos de solicitudes",
        spreadsheet.values_batch_get,
        [
            _sheet_range("Solicitudes_Registros", f"A:{_column_letter(len(REQUEST_HEADERS))}"),
            _sheet_range("Solicitudes_Novedades", f"A:{_column_letter(len(NOVEDADES_HEADERS))}"),
            _sheet_range("Solicitudes_Auditoria", f"A:{_column_letter(len(AUDIT_HEADERS))}"),
        ],
    )
    value_ranges = response.get("valueRanges", []) if isinstance(response, dict) else []

    records_values = value_ranges[0].get("values", []) if len(value_ranges) > 0 else []
    novedades_values = value_ranges[1].get("values", []) if len(value_ranges) > 1 else []
    audit_values = value_ranges[2].get("values", []) if len(value_ranges) > 2 else []

    return {
        "requests": _rows_to_dataframe(records_values, REQUEST_HEADERS),
        "novedades": _rows_to_dataframe(novedades_values, NOVEDADES_HEADERS),
        "audit": _rows_to_dataframe(audit_values, AUDIT_HEADERS),
    }


def get_request_records(worksheet) -> pd.DataFrame:
    records = _run_gspread_call("leer solicitudes", worksheet.get_all_records)
    if not records:
        return pd.DataFrame(columns=REQUEST_HEADERS)
    df = pd.DataFrame(records)
    for header in REQUEST_HEADERS:
        if header not in df.columns:
            df[header] = ""
    return df[REQUEST_HEADERS].copy()


def get_auxiliary_records(worksheet, headers: list[str]) -> pd.DataFrame:
    records = _run_gspread_call("leer datos auxiliares", worksheet.get_all_records)
    if not records:
        return pd.DataFrame(columns=headers)
    df = pd.DataFrame(records)
    for header in headers:
        if header not in df.columns:
            df[header] = ""
    return df[headers].copy()


def build_management_report_rows(df: pd.DataFrame) -> list[list[str]]:
    if df.empty:
        return [REPORT_HEADERS, ["KPI", "Total Solicitudes", "0", "0", "0%"]]

    working_df = df.copy()
    working_df["Estado"] = working_df["Estado"].replace("", "Pendiente").fillna("Pendiente")
    working_df["Tipo_Solicitud"] = working_df["Tipo_Solicitud"].replace("", "Sin tipo").fillna("Sin tipo")
    working_df["Sede"] = working_df["Sede"].replace("", "Sin sede").fillna("Sin sede")
    working_df["Nombre_Completo"] = working_df["Nombre_Completo"].replace("", "Sin nombre").fillna("Sin nombre")
    working_df["Fecha_Solicitud_dt"] = pd.to_datetime(working_df["Fecha_Solicitud"], format="%d/%m/%Y", errors="coerce")
    working_df["Periodo"] = working_df["Fecha_Solicitud_dt"].dt.strftime("%Y-%m").fillna("Sin fecha")
    total = len(working_df)

    rows: list[list[str]] = [REPORT_HEADERS]
    kpis = [
        ["KPI", "Total Solicitudes", str(total), str(total), "100%"],
        ["KPI", "Pendientes", str(int((working_df["Estado"] == "Pendiente").sum())), str(int((working_df["Estado"] == "Pendiente").sum())), _percent((working_df["Estado"] == "Pendiente").sum(), total)],
        ["KPI", "Aprobadas", str(int((working_df["Estado"] == "Aprobada").sum())), str(int((working_df["Estado"] == "Aprobada").sum())), _percent((working_df["Estado"] == "Aprobada").sum(), total)],
        ["KPI", "Negadas", str(int((working_df["Estado"] == "Negada").sum())), str(int((working_df["Estado"] == "Negada").sum())), _percent((working_df["Estado"] == "Negada").sum(), total)],
        ["KPI", "En revision", str(int((working_df["Estado"] == "En revision").sum())), str(int((working_df["Estado"] == "En revision").sum())), _percent((working_df["Estado"] == "En revision").sum(), total)],
    ]
    rows.extend(kpis)

    rows.extend(_group_report_rows(working_df, "Estado", "ESTADO", total))
    rows.extend(_group_report_rows(working_df, "Sede", "SEDE", total))
    rows.extend(_group_report_rows(working_df, "Tipo_Solicitud", "TIPO", total))
    rows.extend(_group_report_rows(working_df, "Nombre_Completo", "EMPLEADO", total))
    rows.extend(_group_report_rows(working_df, "Periodo", "PERIODO", total))

    if working_df["Fecha_Solicitud_dt"].notna().any():
        by_day_df = working_df.dropna(subset=["Fecha_Solicitud_dt"]).copy()
        by_day_df["Dia"] = by_day_df["Fecha_Solicitud_dt"].dt.strftime("%d/%m/%Y")
        by_day = (
            by_day_df.groupby(["Dia", "Fecha_Solicitud_dt"])
            .size()
            .reset_index(name="Cantidad")
            .sort_values(by=["Fecha_Solicitud_dt", "Cantidad"], ascending=[False, False])
        )
        for _, row in by_day.iterrows():
            rows.append(["FECHA", "Dia", str(row["Dia"]), str(int(row["Cantidad"])), _percent(int(row["Cantidad"]), total)])

    return rows


def _percent(value: int | float, total: int | float) -> str:
    if not total:
        return "0%"
    return f"{(float(value) / float(total)) * 100:.1f}%"


def _group_report_rows(df: pd.DataFrame, column_name: str, section_name: str, total: int) -> list[list[str]]:
    grouped = (
        df.groupby(column_name)
        .size()
        .reset_index(name="Cantidad")
        .sort_values(by=["Cantidad", column_name], ascending=[False, True])
    )
    rows: list[list[str]] = []
    for _, row in grouped.iterrows():
        value = str(row[column_name])
        count = int(row["Cantidad"])
        rows.append([section_name, column_name, value, str(count), _percent(count, total)])
    return rows


def refresh_management_report(worksheet, df: pd.DataFrame, force: bool = False) -> bool:
    report_signature = hashlib.sha256(
        df[[column for column in ["Solicitud_ID", "Estado", "Ultima_Actualizacion"] if column in df.columns]]
        .fillna("")
        .astype(str)
        .to_csv(index=False)
        .encode("utf-8")
    ).hexdigest()
    now_ts = time.time()
    last_signature = st.session_state.get("solicitudes_report_signature", "")
    last_synced_at = float(st.session_state.get("solicitudes_report_synced_at", 0.0) or 0.0)
    needs_sync = bool(st.session_state.get("solicitudes_report_needs_sync", True))

    if (
        not force
        and not needs_sync
        and report_signature == last_signature
        and (now_ts - last_synced_at) < SOLICITUDES_REPORT_SYNC_COOLDOWN_SECONDS
    ):
        return False

    rows = build_management_report_rows(df)
    _run_gspread_call("limpiar reporte gerencial", worksheet.clear)
    _run_gspread_call("actualizar reporte gerencial", worksheet.update, "A1", rows)
    st.session_state["solicitudes_report_signature"] = report_signature
    st.session_state["solicitudes_report_synced_at"] = now_ts
    st.session_state["solicitudes_report_needs_sync"] = False
    return True


@st.cache_resource(ttl=600)
def get_moto_inspection_worksheets() -> dict[str, object]:
    spreadsheet = connect_to_base_spreadsheet()
    existing_worksheets = _get_existing_worksheets(spreadsheet)
    profiles_ws = _ensure_worksheet_exists(
        spreadsheet,
        existing_worksheets,
        "InspeccionMotos_Perfiles",
        MOTO_PROFILE_HEADERS,
        rows=3000,
    )
    registros_ws = _ensure_worksheet_exists(
        spreadsheet,
        existing_worksheets,
        "InspeccionMotos_Registros",
        MOTO_INSPECTION_HEADERS,
        rows=8000,
    )

    _ensure_headers_for_sheets(
        {
            "InspeccionMotos_Perfiles": profiles_ws,
            "InspeccionMotos_Registros": registros_ws,
        },
        _get_sheet_previews(
            spreadsheet,
            [
                "InspeccionMotos_Perfiles",
                "InspeccionMotos_Registros",
            ],
        ),
        {
            "InspeccionMotos_Perfiles": MOTO_PROFILE_HEADERS,
            "InspeccionMotos_Registros": MOTO_INSPECTION_HEADERS,
        },
    )

    return {
        "spreadsheet": spreadsheet,
        "profiles": profiles_ws,
        "records": registros_ws,
    }


def get_moto_profile_by_cedula(worksheet, cedula: str) -> dict[str, str] | None:
    lookup_value = _clean_digits(cedula)
    if not lookup_value:
        return None

    records = _run_gspread_call("leer perfiles de inspeccion motos", worksheet.get_all_records)
    if not records:
        return None

    for record in reversed(records):
        if _clean_digits(record.get("Cedula", "")) == lookup_value:
            return {header: _sheet_value(record.get(header, "")) for header in MOTO_PROFILE_HEADERS}
    return None


def upsert_moto_profile(worksheet, profile: dict[str, object]) -> None:
    lookup_value = _clean_digits(profile.get("Cedula", ""))
    if not lookup_value:
        raise ValueError("El perfil de inspeccion requiere una cedula valida.")

    row_values = [_sheet_value(profile.get(header, "")) for header in MOTO_PROFILE_HEADERS]
    records = _run_gspread_call("leer perfiles de inspeccion motos", worksheet.get_all_records)
    existing_row = None
    for index, record in enumerate(records, start=2):
        if _clean_digits(record.get("Cedula", "")) == lookup_value:
            existing_row = index

    if existing_row is None:
        _run_gspread_call("registrar perfil de inspeccion motos", worksheet.append_row, row_values)
        return

    _run_gspread_call(
        "actualizar perfil de inspeccion motos",
        worksheet.update,
        f"A{existing_row}",
        [row_values],
    )


def append_moto_inspection_record(worksheet, record: dict[str, object]) -> None:
    _run_gspread_call(
        "registrar inspeccion preoperacional de motos",
        worksheet.append_row,
        [_sheet_value(record.get(header, "")) for header in MOTO_INSPECTION_HEADERS],
    )


def get_last_moto_inspection_record(worksheet, cedula: str, plate: str = "") -> dict[str, str] | None:
    lookup_value = _clean_digits(cedula)
    plate_lookup = _normalize_text(plate)
    if not lookup_value:
        return None

    records = _run_gspread_call("leer historial de inspeccion motos", worksheet.get_all_records)
    if not records:
        return None

    for record in reversed(records):
        same_cedula = _clean_digits(record.get("Cedula", "")) == lookup_value
        if not same_cedula:
            continue
        if plate_lookup and _normalize_text(record.get("Placa_Motocicleta", "")) != plate_lookup:
            continue
        return {header: _sheet_value(record.get(header, "")) for header in MOTO_INSPECTION_HEADERS}
    return None


def _email_settings() -> dict[str, str]:
    settings = st.secrets.get("email", {}) or st.secrets.get("email_credentials", {})
    return {
        "sender_email": settings.get("sender_email", ""),
        "sender_password": settings.get("sender_password", ""),
        "permissions_recipient": settings.get(
            "permissions_recipient",
            settings.get("recipient_email", "talentohumano@ferreinox.co"),
        ),
    }


def _storage_settings() -> dict[str, str]:
    settings = st.secrets.get("storage", {})
    return {
        "dropbox_access_token": settings.get("dropbox_access_token", ""),
        "dropbox_folder": settings.get("dropbox_folder", "/ferreinox/solicitudes"),
    }


def upload_request_attachment(uploaded_file, request_id: str) -> tuple[bool, dict[str, str]]:
    settings = _storage_settings()
    access_token = settings["dropbox_access_token"]
    if not uploaded_file:
        return True, {
            "Adjunto_Nombre": "",
            "Adjunto_URL": "",
            "Adjunto_Storage": "",
            "Adjunto_Estado": "SIN_ADJUNTO",
        }

    if not access_token:
        return False, {
            "Adjunto_Nombre": uploaded_file.name,
            "Adjunto_URL": "",
            "Adjunto_Storage": "DROPBOX_NO_CONFIGURADO",
            "Adjunto_Estado": "PENDIENTE_CONFIGURACION",
        }

    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", uploaded_file.name)
    dropbox_path = f"{settings['dropbox_folder'].rstrip('/')}/{request_id}_{safe_name}"

    try:
        client = dropbox.Dropbox(access_token)
        client.files_upload(uploaded_file.getvalue(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)

        try:
            shared_link = client.sharing_create_shared_link_with_settings(dropbox_path).url
        except ApiError:
            shared_links = client.sharing_list_shared_links(path=dropbox_path, direct_only=True).links
            shared_link = shared_links[0].url if shared_links else ""

        shared_link = shared_link.replace("?dl=0", "?raw=1") if shared_link else ""
        return True, {
            "Adjunto_Nombre": safe_name,
            "Adjunto_URL": shared_link,
            "Adjunto_Storage": "DROPBOX",
            "Adjunto_Estado": "CARGADO",
        }
    except Exception as error:
        return False, {
            "Adjunto_Nombre": safe_name,
            "Adjunto_URL": "",
            "Adjunto_Storage": "DROPBOX_ERROR",
            "Adjunto_Estado": str(error),
        }


def _send_email(to: str, subject: str, contents: str) -> tuple[bool, str]:
    settings = _email_settings()
    sender_email = settings["sender_email"]
    sender_password = settings["sender_password"]
    if not sender_email or not sender_password:
        return False, "No se encontraron credenciales de correo en st.secrets['email'] ni en st.secrets['email_credentials']."

    try:
        yag = yagmail.SMTP(sender_email, sender_password)
        yag.send(to=to, subject=subject, contents=contents)
    except smtplib.SMTPAuthenticationError:
        return False, "La autenticacion del correo fallo. Revise la cuenta y la clave de aplicacion."
    except Exception as error:
        return False, str(error)
    return True, ""


def _request_email_body(
    record: dict[str, str],
    heading: str,
    footer: str = "",
    action_url: str = "",
    action_label: str = "",
) -> str:
    detail_rows = [
        ("Solicitud", record.get("Solicitud_ID", "")),
        ("Empleado", record.get("Nombre_Completo", "")),
        ("Cedula", record.get("Cedula", "")),
        ("Cargo", record.get("Cargo", "")),
        ("Sede", record.get("Sede", "")),
        ("Tipo", record.get("Tipo_Solicitud", "")),
        ("Motivo", record.get("Motivo_Descripcion", "")),
        ("Fecha inicial", record.get("Fecha_Inicial", "")),
        ("Fecha final", record.get("Fecha_Final", "")),
        ("Hora de salida", record.get("Hora_Salida", "")),
        ("Tiempo total", record.get("Tiempo_Total", "")),
        ("Persona a cargo", record.get("Persona_A_Cargo", "")),
        ("Detalle", record.get("Detalle_Solicitud", "")),
        ("Estado", record.get("Estado", "")),
        ("Adjunto", record.get("Adjunto_URL", "")),
    ]
    rows_html = "".join(
        f"<tr><td style='padding:8px;border:1px solid #d7e3eb;font-weight:700;background:#f4f8fb;'>{html.escape(label)}</td><td style='padding:8px;border:1px solid #d7e3eb;'>{html.escape(value or '')}</td></tr>"
        for label, value in detail_rows
    )
    action_html = ""
    if action_url:
        action_html = f"""
        <div style='margin-top:1rem;padding:1rem 1.2rem;border-radius:16px;background:#eef6fb;border:1px solid #cfe2ef;'>
            <p style='margin:0 0 0.8rem 0;font-weight:700;color:#0b3954;'>Acceso directo para gestion</p>
            <a href='{html.escape(action_url)}' style='display:inline-block;padding:0.8rem 1.1rem;background:#0b3954;color:#ffffff;text-decoration:none;border-radius:12px;font-weight:700;'>
                {html.escape(action_label or 'Abrir portal de gestion')}
            </a>
            <p style='margin:0.8rem 0 0 0;font-size:0.85rem;color:#557085;'>Si el boton no abre, copie este enlace en el navegador:<br>{html.escape(action_url)}</p>
        </div>
        """
    return f"""
    <div style='font-family:Segoe UI, Arial, sans-serif; color:#183b56;'>
        <h2 style='margin-bottom:0.5rem;'>{html.escape(heading)}</h2>
        <table style='border-collapse:collapse; width:100%;'>
            {rows_html}
        </table>
        {action_html}
        <p style='margin-top:1rem;'>{html.escape(footer)}</p>
    </div>
    """


def send_request_email(record: dict[str, str]) -> tuple[bool, str]:
    recipient = _email_settings()["permissions_recipient"]
    subject = f"Nueva solicitud {record.get('Tipo_Solicitud', 'Permiso')} - {record.get('Solicitud_ID', '')}"
    body = _request_email_body(
        record,
        "Nueva solicitud registrada en Ferreinox",
        "Revise la solicitud en la pagina administrativa para aprobarla o negarla.",
        action_url=_approval_review_url(),
        action_label="Abrir enlace de revision y aprobacion",
    )
    return _send_email(recipient, subject, body)


def send_employee_response_email(record: dict[str, str]) -> tuple[bool, str]:
    recipient = record.get("Correo_Empleado", "")
    if not recipient:
        return False, "El empleado no tiene correo electronico registrado."
    subject = f"Respuesta a la solicitud {record.get('Solicitud_ID', '')}"
    body = _request_email_body(
        record,
        f"Su solicitud fue {record.get('Estado', '').lower()}",
        record.get("Observaciones_RRHH", "Sin observaciones adicionales."),
    )
    return _send_email(recipient, subject, body)