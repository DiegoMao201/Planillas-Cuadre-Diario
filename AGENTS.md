# Contexto Operativo Ferreinox

## Objetivo del repositorio

Este repositorio centraliza los flujos internos de Ferreinox para:

- planillas de cuadre diario de caja
- recibos de caja
- viaticos
- solicitudes de permisos, vacaciones y licencias
- aprobacion administrativa y reportes gerenciales de solicitudes

## Estructura clave

- `Planillas.py`: modulo principal de cuadre diario
- `pages/1_Recibos_de_Caja.py`: modulo de recibos de caja
- `pages/2_Viaticos.py`: modulo de viaticos
- `pages/3_Solicitudes_de_Permisos.py`: formulario abierto para empleados
- `pages/4_Gestion_de_Solicitudes.py`: vista administrativa de aprobacion, reportes y respuestas
- `app_shared.py`: autenticacion por roles, navegacion, integracion con Google Sheets, correo, Dropbox y lectura del Excel maestro de empleados
- `base_datos_empleados.xlsx`: base maestra local de empleados usada para autocompletar por cedula

## Reglas actuales de acceso

- `credentials.hashed_password`
  - acceso solo a `Planillas.py` y `pages/1_Recibos_de_Caja.py`
- `credentials.admin_hashed_password`
  - acceso total a toda la app
  - incluye viaticos y gestion de solicitudes
- `pages/3_Solicitudes_de_Permisos.py`
  - acceso abierto para empleados sin clave

## Secretos requeridos en Streamlit

### Credenciales

```toml
[credentials]
hashed_password = "HASH_OPERACIONES"
admin_hashed_password = "HASH_ADMIN"
```

### Google Sheets

```toml
[google_credentials]
# credenciales JSON de la cuenta de servicio

[google_sheets]
spreadsheet_name = "Planillas_Ferreinox"
registros_sheet_name = "Registros"
config_sheet_name = "Configuracion"
```

### Correo

```toml
[email]
sender_email = "correo@empresa.com"
sender_password = "clave_aplicacion"
permissions_recipient = "talentohumano@ferreinox.co"
```

Tambien se acepta este formato alterno:

```toml
[email_credentials]
sender_email = "correo@empresa.com"
sender_password = "clave_aplicacion"
recipient_email = "talentohumano@ferreinox.co"
```

### Adjuntos

```toml
[storage]
dropbox_access_token = "TOKEN_DROPBOX"
dropbox_folder = "/ferreinox/solicitudes"
```

## Hojas que la app crea o usa

### Caja y operaciones existentes

- `Registros`
- `Configuracion`
- `Consecutivos`
- `GlobalConsecutivo`
- `RegistrosRecibos`
- `Viaticos_Registros`
- `Viaticos_Consecutivos`

### Solicitudes nuevas

- `Solicitudes_Registros`
- `Solicitudes_Novedades`
- `Solicitudes_Auditoria`
- `Solicitudes_Parametros`
- `Solicitudes_Reporte_Gerencia`

## Reporte gerencial automático

La hoja `Solicitudes_Reporte_Gerencia` se refresca desde la vista administrativa y contiene:

- KPI total
- pendientes
- aprobadas
- negadas
- en revision
- agrupacion por estado
- agrupacion por sede
- agrupacion por tipo de solicitud
- agrupacion por empleado
- agrupacion por periodo mensual
- agrupacion por fecha diaria

Formato de columnas:

- `Seccion`
- `Dimension`
- `Valor`
- `Cantidad`
- `Porcentaje`

## Base de empleados

La app busca `base_datos_empleados.xlsx` en este orden:

1. raiz del repositorio
2. `data/base_datos_empleados.xlsx`
3. carpeta padre del repositorio

Para despliegue confiable se recomienda dejarlo dentro de la raiz del repositorio.

## Problema ya resuelto

Si en `Planillas.py` el usuario cambia la fecha y vuelve al login, la causa era que `clear_form_state()` borraba `access_role` del `session_state`. Eso ya fue corregido y no se debe revertir.

## Criterios de mantenimiento

- no guardar archivos binarios en Google Sheets
- guardar adjuntos en Dropbox y solo registrar metadata y URL en Sheets
- mantener roles separados entre operacion y administracion
- conservar la pagina de solicitudes de permisos como acceso abierto para empleados
- si se cambia la estructura de columnas del Excel maestro, revisar `load_employee_master()` en `app_shared.py`

## Si se abre un nuevo contexto de IA

Al iniciar, revisar primero:

1. `AGENTS.md`
2. `app_shared.py`
3. `pages/3_Solicitudes_de_Permisos.py`
4. `pages/4_Gestion_de_Solicitudes.py`
5. estado de `st.secrets`

Preguntas clave antes de tocar nada:

1. se esta trabajando local o en Streamlit Cloud
2. el archivo `base_datos_empleados.xlsx` esta actualizado
3. las hojas de Google Sheets ya existen o deben autogenerarse
4. Dropbox y correo ya estan configurados
5. el cambio afecta acceso operativo, administrativo o formulario publico