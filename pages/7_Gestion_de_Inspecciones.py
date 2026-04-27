from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app_shared import (
    MOTO_INSPECTION_HEADERS,
    MOTO_PROFILE_HEADERS,
    VEHICLE_INSPECTION_HEADERS,
    VEHICLE_PROFILE_HEADERS,
    current_colombia_date,
    get_inspection_records,
    get_moto_inspection_worksheets,
    get_vehicle_inspection_worksheets,
    inject_shared_css,
    load_employee_master,
    render_brand_header,
    render_sidebar,
    require_access,
)


st.set_page_config(layout="wide", page_title="Gestion de inspecciones")

NAVY = "0B3954"
ORANGE = "E67E22"
TEAL = "1F7A8C"
RED = "C0392B"
TEXT = "183B56"
LIGHT = "F4F8FB"

MOTO_ROLE_OPTIONS = {"MENSAJEROS", "ASESOR COMERCIAL EXTERNO", "VENDEDOR EXTERNO"}
VEHICLE_ROLE_OPTIONS = {"CONDUCTOR", "LIDER COMERCIAL", "VENDEDOR EXTERNO"}


def inject_dashboard_css() -> None:
    st.markdown(
        f"""
        <style>
        .gx-hero {{
            background: linear-gradient(135deg, #{NAVY} 0%, #165a7f 55%, #{TEAL} 100%);
            border-radius: 24px;
            padding: 1.5rem 1.6rem;
            color: #ffffff;
            box-shadow: 0 18px 38px rgba(11, 57, 84, 0.18);
            margin-bottom: 1rem;
        }}
        .gx-hero h2 {{ margin: 0; font-size: 1.45rem; font-weight: 800; }}
        .gx-hero p {{ margin: 0.45rem 0 0 0; color: rgba(255,255,255,0.88); max-width: 940px; }}
        .gx-kpi {{
            border-radius: 18px;
            padding: 1rem 1.05rem;
            background: #ffffff;
            border: 1px solid rgba(11, 57, 84, 0.08);
            box-shadow: 0 12px 26px rgba(11, 57, 84, 0.06);
            min-height: 132px;
        }}
        .gx-kpi .label {{ color: #5f7a8d; text-transform: uppercase; font-size: 0.75rem; font-weight: 800; }}
        .gx-kpi .value {{ color: #{TEXT}; font-size: 1.95rem; line-height: 1.05; font-weight: 800; margin-top: 0.45rem; }}
        .gx-kpi .note {{ color: #688397; font-size: 0.86rem; margin-top: 0.45rem; }}
        .gx-kpi.navy {{ border-top: 5px solid #{NAVY}; }}
        .gx-kpi.orange {{ border-top: 5px solid #{ORANGE}; }}
        .gx-kpi.teal {{ border-top: 5px solid #{TEAL}; }}
        .gx-kpi.red {{ border-top: 5px solid #{RED}; }}
        .gx-panel {{
            border-radius: 20px;
            padding: 1.15rem 1.2rem;
            background: linear-gradient(180deg, #ffffff 0%, #{LIGHT} 100%);
            border: 1px solid rgba(11, 57, 84, 0.08);
            box-shadow: 0 12px 28px rgba(11, 57, 84, 0.06);
        }}
        .gx-panel h3 {{ margin: 0 0 0.25rem 0; color: #{TEXT}; }}
        .gx-panel p {{ margin: 0; color: #688397; font-size: 0.88rem; }}
        .gx-chip-row {{ display:flex; flex-wrap:wrap; gap:0.5rem; margin-top:0.9rem; }}
        .gx-chip {{ background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.18); border-radius: 999px; padding: 0.35rem 0.8rem; font-size: 0.82rem; font-weight: 700; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_kpi(label: str, value: str, note: str, tone: str) -> None:
    st.markdown(
        f"""
        <div class="gx-kpi {tone}">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            <div class="note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _normalize_role(value: object) -> str:
    return str(value or "").strip().upper()


def _prepare_inspection_records(df: pd.DataFrame, inspection_type: str) -> pd.DataFrame:
    working_df = df.copy()
    if working_df.empty:
        working_df["Fecha_Inspeccion_dt"] = pd.NaT
        working_df["Fecha_Registro_dt"] = pd.NaT
        working_df["Tipo_Inspeccion"] = inspection_type
        return working_df

    for column in working_df.columns:
        working_df[column] = working_df[column].fillna("").astype(str)
    working_df["Fecha_Inspeccion_dt"] = pd.to_datetime(working_df["Fecha_Inspeccion"], format="%d/%m/%Y", errors="coerce")
    working_df["Fecha_Registro_dt"] = pd.to_datetime(working_df["Fecha_Registro"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    working_df["Tipo_Inspeccion"] = inspection_type
    return working_df


def _prepare_profiles(df: pd.DataFrame, inspection_type: str) -> pd.DataFrame:
    working_df = df.copy()
    if working_df.empty:
        working_df["Tipo_Inspeccion"] = inspection_type
        return working_df
    for column in working_df.columns:
        working_df[column] = working_df[column].fillna("").astype(str)
    working_df["Tipo_Inspeccion"] = inspection_type
    return working_df


def _employee_catalog_from_master(master_df: pd.DataFrame) -> pd.DataFrame:
    tracked_roles = MOTO_ROLE_OPTIONS | VEHICLE_ROLE_OPTIONS
    working_df = master_df.copy()
    working_df["cargo_normalizado"] = working_df["cargo"].map(_normalize_role)
    filtered_df = working_df[working_df["cargo_normalizado"].isin(tracked_roles)].copy()
    if filtered_df.empty:
        return pd.DataFrame(columns=["Cedula", "Empleado", "Cargo", "Sede", "Tipo_Inspeccion"])

    rows: list[dict[str, str]] = []
    for _, row in filtered_df.iterrows():
        role = row.get("cargo_normalizado", "")
        if role in MOTO_ROLE_OPTIONS:
            rows.append(
                {
                    "Cedula": str(row.get("cedula", "")).strip(),
                    "Empleado": str(row.get("nombre_completo", "")).strip(),
                    "Cargo": str(row.get("cargo", "")).strip(),
                    "Sede": str(row.get("sede", "")).strip(),
                    "Tipo_Inspeccion": "Motos",
                }
            )
        if role in VEHICLE_ROLE_OPTIONS:
            rows.append(
                {
                    "Cedula": str(row.get("cedula", "")).strip(),
                    "Empleado": str(row.get("nombre_completo", "")).strip(),
                    "Cargo": str(row.get("cargo", "")).strip(),
                    "Sede": str(row.get("sede", "")).strip(),
                    "Tipo_Inspeccion": "Vehiculos",
                }
            )
    return pd.DataFrame(rows).drop_duplicates(subset=["Cedula", "Tipo_Inspeccion"])


def _supplement_catalog(catalog_df: pd.DataFrame, profiles_df: pd.DataFrame, records_df: pd.DataFrame, inspection_type: str, name_col: str, cargo_col: str, sede_col: str) -> pd.DataFrame:
    supplemental_rows: list[dict[str, str]] = []
    for source_df in [profiles_df, records_df]:
        if source_df.empty:
            continue
        for _, row in source_df.iterrows():
            cedula = str(row.get("Cedula", "")).strip()
            if not cedula:
                continue
            supplemental_rows.append(
                {
                    "Cedula": cedula,
                    "Empleado": str(row.get(name_col, "")).strip(),
                    "Cargo": str(row.get(cargo_col, "")).strip(),
                    "Sede": str(row.get(sede_col, "")).strip(),
                    "Tipo_Inspeccion": inspection_type,
                }
            )
    if not supplemental_rows:
        return catalog_df
    supplement_df = pd.DataFrame(supplemental_rows).drop_duplicates(subset=["Cedula", "Tipo_Inspeccion"])
    combined_df = pd.concat([catalog_df, supplement_df], ignore_index=True)
    combined_df.sort_values(by=["Tipo_Inspeccion", "Empleado", "Cedula"], inplace=True)
    return combined_df.drop_duplicates(subset=["Cedula", "Tipo_Inspeccion"], keep="first")


def _document_status(date_value: str, today: date, threshold_days: int = 30) -> str:
    if not str(date_value).strip():
        return "Sin fecha"
    parsed = pd.to_datetime(str(date_value), format="%d/%m/%Y", errors="coerce")
    if pd.isna(parsed):
        return "Sin fecha"
    doc_date = parsed.date()
    if doc_date < today:
        return "Vencido"
    if doc_date <= today + timedelta(days=threshold_days):
        return "Por vencer"
    return "Al dia"


def build_document_alerts(moto_profiles_df: pd.DataFrame, vehicle_profiles_df: pd.DataFrame, today: date) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    if not moto_profiles_df.empty:
        for _, row in moto_profiles_df.iterrows():
            rows.extend(
                [
                    {
                        "Tipo_Inspeccion": "Motos",
                        "Cedula": row.get("Cedula", ""),
                        "Empleado": row.get("Nombre_Conductor", ""),
                        "Cargo": row.get("Cargo_Conductor", ""),
                        "Sede": row.get("Sede", ""),
                        "Documento": "SOAT",
                        "Fecha_Vencimiento": row.get("Fecha_Vencimiento_SOAT", ""),
                        "Estado_Documental": _document_status(row.get("Fecha_Vencimiento_SOAT", ""), today),
                    },
                    {
                        "Tipo_Inspeccion": "Motos",
                        "Cedula": row.get("Cedula", ""),
                        "Empleado": row.get("Nombre_Conductor", ""),
                        "Cargo": row.get("Cargo_Conductor", ""),
                        "Sede": row.get("Sede", ""),
                        "Documento": "Tecnomecanica",
                        "Fecha_Vencimiento": row.get("Fecha_Vencimiento_Tecnomecanica", ""),
                        "Estado_Documental": _document_status(row.get("Fecha_Vencimiento_Tecnomecanica", ""), today),
                    },
                ]
            )
    if not vehicle_profiles_df.empty:
        for _, row in vehicle_profiles_df.iterrows():
            rows.extend(
                [
                    {
                        "Tipo_Inspeccion": "Vehiculos",
                        "Cedula": row.get("Cedula", ""),
                        "Empleado": row.get("Nombre_Conductor", ""),
                        "Cargo": row.get("Cargo_Conductor", ""),
                        "Sede": row.get("Sede", ""),
                        "Documento": "SOAT",
                        "Fecha_Vencimiento": row.get("Fecha_Vencimiento_SOAT", ""),
                        "Estado_Documental": _document_status(row.get("Fecha_Vencimiento_SOAT", ""), today),
                    },
                    {
                        "Tipo_Inspeccion": "Vehiculos",
                        "Cedula": row.get("Cedula", ""),
                        "Empleado": row.get("Nombre_Conductor", ""),
                        "Cargo": row.get("Cargo_Conductor", ""),
                        "Sede": row.get("Sede", ""),
                        "Documento": "Tecnomecanica",
                        "Fecha_Vencimiento": row.get("Fecha_Vencimiento_Tecnomecanica", ""),
                        "Estado_Documental": _document_status(row.get("Fecha_Vencimiento_Tecnomecanica", ""), today),
                    },
                    {
                        "Tipo_Inspeccion": "Vehiculos",
                        "Cedula": row.get("Cedula", ""),
                        "Empleado": row.get("Nombre_Conductor", ""),
                        "Cargo": row.get("Cargo_Conductor", ""),
                        "Sede": row.get("Sede", ""),
                        "Documento": "Extintor",
                        "Fecha_Vencimiento": row.get("Fecha_Vencimiento_Extintor", ""),
                        "Estado_Documental": _document_status(row.get("Fecha_Vencimiento_Extintor", ""), today),
                    },
                ]
            )

    if not rows:
        return pd.DataFrame(columns=["Tipo_Inspeccion", "Cedula", "Empleado", "Cargo", "Sede", "Documento", "Fecha_Vencimiento", "Estado_Documental"])
    alerts_df = pd.DataFrame(rows)
    severity_map = {"Vencido": 0, "Por vencer": 1, "Sin fecha": 2, "Al dia": 3}
    alerts_df["_severity"] = alerts_df["Estado_Documental"].map(severity_map).fillna(4)
    alerts_df.sort_values(by=["_severity", "Tipo_Inspeccion", "Empleado", "Documento"], inplace=True)
    return alerts_df.drop(columns=["_severity"])


def build_compliance_df(catalog_df: pd.DataFrame, records_df: pd.DataFrame, selected_date: date, plate_column: str) -> pd.DataFrame:
    if catalog_df.empty:
        return pd.DataFrame(columns=["Tipo_Inspeccion", "Cedula", "Empleado", "Cargo", "Sede", "Estado_Fecha", "Placa", "Registros_En_Fecha"])

    daily_records_df = records_df[records_df["Fecha_Inspeccion_dt"].dt.date == selected_date].copy() if not records_df.empty else pd.DataFrame(columns=records_df.columns)
    if not daily_records_df.empty:
        grouped = (
            daily_records_df.groupby(["Tipo_Inspeccion", "Cedula"]).agg(
                Registros_En_Fecha=("Inspeccion_ID", "count"),
                Placa=(plate_column, lambda values: ", ".join(sorted({str(value).strip() for value in values if str(value).strip()}))),
            )
        ).reset_index()
    else:
        grouped = pd.DataFrame(columns=["Tipo_Inspeccion", "Cedula", "Registros_En_Fecha", "Placa"])

    merged_df = catalog_df.merge(grouped, how="left", on=["Tipo_Inspeccion", "Cedula"])
    merged_df["Registros_En_Fecha"] = merged_df["Registros_En_Fecha"].fillna(0).astype(int)
    merged_df["Placa"] = merged_df["Placa"].fillna("")
    merged_df["Estado_Fecha"] = merged_df["Registros_En_Fecha"].map(
        lambda count: "Duplicada" if count > 1 else ("Registrada" if count == 1 else "Faltante")
    )
    merged_df.sort_values(by=["Estado_Fecha", "Tipo_Inspeccion", "Empleado", "Sede"], inplace=True)
    return merged_df


def main() -> None:
    require_access(
        "admin",
        "Gestion de inspecciones",
        "Vista administrativa para cumplimiento diario, alertas documentales y control ejecutivo de inspecciones de motos y vehiculos.",
    )
    inject_shared_css()
    inject_dashboard_css()
    render_sidebar("Gestion de inspecciones")
    render_brand_header(
        "Centro Gerencial de Inspecciones",
        "Panel administrativo para ver cumplimiento diario, faltantes por fecha y alertas de documentacion por empleado.",
    )

    today = current_colombia_date()
    st.markdown(
        f"""
        <div class="gx-hero">
            <h2>Inspecciones preoperacionales con foco operativo</h2>
            <p>Esta vista responde tres necesidades de control: saber quien ya diligencio hoy, detectar faltantes por fecha y vigilar documentos vencidos o proximos a vencer por empleado.</p>
            <div class="gx-chip-row">
                <span class="gx-chip">Corte Colombia: {today.strftime('%d/%m/%Y')}</span>
                <span class="gx-chip">Uso exclusivo administrador</span>
                <span class="gx-chip">Motos y vehiculos en un solo panel</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        moto_ws = get_moto_inspection_worksheets()
        vehicle_ws = get_vehicle_inspection_worksheets()
        moto_records_df = _prepare_inspection_records(get_inspection_records(moto_ws["records"], MOTO_INSPECTION_HEADERS), "Motos")
        vehicle_records_df = _prepare_inspection_records(get_inspection_records(vehicle_ws["records"], VEHICLE_INSPECTION_HEADERS), "Vehiculos")
        moto_profiles_df = _prepare_profiles(get_inspection_records(moto_ws["profiles"], MOTO_PROFILE_HEADERS), "Motos")
        vehicle_profiles_df = _prepare_profiles(get_inspection_records(vehicle_ws["profiles"], VEHICLE_PROFILE_HEADERS), "Vehiculos")
        master_df = load_employee_master()
    except Exception as error:
        st.error(f"No se pudieron cargar los datos administrativos de inspecciones: {error}")
        return

    inspection_records_df = pd.concat([moto_records_df, vehicle_records_df], ignore_index=True, sort=False)
    document_alerts_df = build_document_alerts(moto_profiles_df, vehicle_profiles_df, today)

    base_catalog_df = _employee_catalog_from_master(master_df)
    moto_catalog_df = _supplement_catalog(
        base_catalog_df[base_catalog_df["Tipo_Inspeccion"] == "Motos"].copy(),
        moto_profiles_df,
        moto_records_df,
        "Motos",
        "Nombre_Conductor",
        "Cargo_Conductor",
        "Sede",
    )
    vehicle_catalog_df = _supplement_catalog(
        base_catalog_df[base_catalog_df["Tipo_Inspeccion"] == "Vehiculos"].copy(),
        vehicle_profiles_df,
        vehicle_records_df,
        "Vehiculos",
        "Nombre_Conductor",
        "Cargo_Conductor",
        "Sede",
    )
    compliance_catalog_df = pd.concat([moto_catalog_df, vehicle_catalog_df], ignore_index=True).drop_duplicates(subset=["Cedula", "Tipo_Inspeccion"])

    selected_date = st.date_input("Fecha a revisar", value=today, format="DD/MM/YYYY")
    if inspection_records_df.empty:
        st.warning("Aun no existen inspecciones registradas. El panel administrativo se habilitara automaticamente cuando entren los primeros datos.")
        return

    daily_compliance_df = build_compliance_df(
        compliance_catalog_df,
        pd.concat(
            [
                moto_records_df.assign(Placa_Referencia=moto_records_df.get("Placa_Motocicleta", "")),
                vehicle_records_df.assign(Placa_Referencia=vehicle_records_df.get("Placa_Vehiculo", "")),
            ],
            ignore_index=True,
            sort=False,
        ),
        selected_date,
        "Placa_Referencia",
    )

    todays_records_df = inspection_records_df[inspection_records_df["Fecha_Inspeccion_dt"].dt.date == today].copy()
    today_completed = int((daily_compliance_df["Estado_Fecha"] == "Registrada").sum()) if not daily_compliance_df.empty else 0
    today_missing = int((daily_compliance_df["Estado_Fecha"] == "Faltante").sum()) if not daily_compliance_df.empty else 0
    today_duplicates = int((daily_compliance_df["Estado_Fecha"] == "Duplicada").sum()) if not daily_compliance_df.empty else 0
    document_risk = document_alerts_df[document_alerts_df["Estado_Documental"].isin(["Vencido", "Por vencer", "Sin fecha"])]

    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        render_kpi("Inspecciones hoy", str(len(todays_records_df)), "Registros con fecha de hoy en Colombia", "navy")
    with kpi_cols[1]:
        render_kpi("Empleados al dia", str(today_completed), "Cumplieron inspeccion en la fecha revisada", "teal")
    with kpi_cols[2]:
        render_kpi("Faltantes", str(today_missing), "Empleados sin inspeccion en la fecha revisada", "orange")
    with kpi_cols[3]:
        render_kpi("Alertas documentales", str(len(document_risk)), "Vencidos, por vencer o sin fecha registrada", "red")

    top_cols = st.columns([1.1, 1])
    with top_cols[0]:
        st.markdown("#### Faltantes y duplicados por fecha")
        focus_df = daily_compliance_df[daily_compliance_df["Estado_Fecha"].isin(["Faltante", "Duplicada"])].copy()
        if focus_df.empty:
            st.info("No hay faltantes ni duplicados para la fecha seleccionada.")
        else:
            st.dataframe(
                focus_df[["Tipo_Inspeccion", "Cedula", "Empleado", "Cargo", "Sede", "Estado_Fecha", "Placa", "Registros_En_Fecha"]],
                use_container_width=True,
                hide_index=True,
            )
    with top_cols[1]:
        st.markdown("#### Alertas documentales prioritarias")
        if document_risk.empty:
            st.info("No hay alertas documentales prioritarias en este momento.")
        else:
            st.dataframe(
                document_risk[["Tipo_Inspeccion", "Empleado", "Cedula", "Sede", "Documento", "Fecha_Vencimiento", "Estado_Documental"]].head(15),
                use_container_width=True,
                hide_index=True,
            )

    tabs = st.tabs(["Resumen", "Cumplimiento Diario", "Alertas Documentales", "Revision Detallada"])

    with tabs[0]:
        panel_cols = st.columns(2)
        with panel_cols[0]:
            st.markdown("#### Registros por fecha")
            by_day_df = (
                inspection_records_df.dropna(subset=["Fecha_Inspeccion_dt"])
                .assign(Dia=lambda df: df["Fecha_Inspeccion_dt"].dt.strftime("%d/%m/%Y"))
                .groupby(["Dia", "Fecha_Inspeccion_dt"])
                .size()
                .reset_index(name="Cantidad")
                .sort_values(by="Fecha_Inspeccion_dt")
            )
            if by_day_df.empty:
                st.caption("Sin datos para graficar.")
            else:
                st.bar_chart(by_day_df.set_index("Dia")["Cantidad"], use_container_width=True)
        with panel_cols[1]:
            st.markdown("#### Distribucion por tipo de inspeccion")
            type_summary = inspection_records_df.groupby("Tipo_Inspeccion").size().reset_index(name="Cantidad")
            if type_summary.empty:
                st.caption("Sin datos para graficar.")
            else:
                st.bar_chart(type_summary.set_index("Tipo_Inspeccion")["Cantidad"], use_container_width=True)

        st.markdown("#### Ultimos registros")
        recent_columns = [
            "Tipo_Inspeccion",
            "Fecha_Inspeccion",
            "Nombre_Conductor",
            "Cedula",
            "Cargo_Conductor",
            "Sede",
        ]
        if "Placa_Motocicleta" in inspection_records_df.columns or "Placa_Vehiculo" in inspection_records_df.columns:
            inspection_records_df["Placa_Resumen"] = inspection_records_df.get("Placa_Motocicleta", "")
            vehicle_mask = inspection_records_df["Tipo_Inspeccion"] == "Vehiculos"
            inspection_records_df.loc[vehicle_mask, "Placa_Resumen"] = inspection_records_df.loc[vehicle_mask, "Placa_Vehiculo"]
            recent_columns.append("Placa_Resumen")
        st.dataframe(
            inspection_records_df.sort_values(by=["Fecha_Registro_dt", "Fecha_Inspeccion_dt"], ascending=[False, False])[recent_columns].head(20),
            use_container_width=True,
            hide_index=True,
        )

    with tabs[1]:
        st.markdown("#### Estado por empleado en la fecha seleccionada")
        type_filter = st.selectbox("Tipo de inspeccion", ["Todas", "Motos", "Vehiculos"], key="inspection_admin_type_filter")
        compliance_view_df = daily_compliance_df.copy()
        if type_filter != "Todas":
            compliance_view_df = compliance_view_df[compliance_view_df["Tipo_Inspeccion"] == type_filter]
        state_filter = st.selectbox("Estado", ["Todos", "Registrada", "Faltante", "Duplicada"], key="inspection_admin_state_filter")
        if state_filter != "Todos":
            compliance_view_df = compliance_view_df[compliance_view_df["Estado_Fecha"] == state_filter]
        st.dataframe(
            compliance_view_df[["Tipo_Inspeccion", "Cedula", "Empleado", "Cargo", "Sede", "Estado_Fecha", "Placa", "Registros_En_Fecha"]],
            use_container_width=True,
            hide_index=True,
        )

    with tabs[2]:
        st.markdown("#### Revision documental por empleado")
        doc_type_filter = st.selectbox("Estado documental", ["Todos", "Vencido", "Por vencer", "Sin fecha", "Al dia"], key="inspection_admin_doc_state")
        doc_view_df = document_alerts_df.copy()
        if doc_type_filter != "Todos":
            doc_view_df = doc_view_df[doc_view_df["Estado_Documental"] == doc_type_filter]
        st.dataframe(
            doc_view_df[["Tipo_Inspeccion", "Empleado", "Cedula", "Cargo", "Sede", "Documento", "Fecha_Vencimiento", "Estado_Documental"]],
            use_container_width=True,
            hide_index=True,
        )

    with tabs[3]:
        detail_type = st.selectbox("Ver registros de", ["Motos", "Vehiculos"], key="inspection_admin_detail_type")
        detail_df = moto_records_df.copy() if detail_type == "Motos" else vehicle_records_df.copy()
        if detail_df.empty:
            st.info(f"No hay registros de {detail_type.lower()} para revisar.")
        else:
            detail_name_col = "Nombre_Conductor"
            detail_plate_col = "Placa_Motocicleta" if detail_type == "Motos" else "Placa_Vehiculo"
            detail_cols = [
                "Fecha_Inspeccion",
                detail_name_col,
                "Cedula",
                "Cargo_Conductor",
                "Sede",
                detail_plate_col,
                "Fecha_Vencimiento_SOAT",
                "Fecha_Vencimiento_Tecnomecanica",
            ]
            if detail_type == "Vehiculos":
                detail_cols.append("Fecha_Vencimiento_Extintor")
            st.dataframe(
                detail_df.sort_values(by=["Fecha_Registro_dt", "Fecha_Inspeccion_dt"], ascending=[False, False])[detail_cols],
                use_container_width=True,
                hide_index=True,
            )


if __name__ == "__main__":
    main()