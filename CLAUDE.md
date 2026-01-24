# CLAUDE.md — Guía para Claude Code en este repo

Este repositorio contiene un **módulo custom de Odoo 17** llamado `pagos_en_facturas` desarrollado por GuvensConsultora.
Objetivo: registrar pagos directamente en facturas con múltiples medios (efectivo, Mercado Pago, tarjeta) y cumplir normativa AFIP.

---

## Reglas de trabajo (calidad + mínimo tokens)

- **Cambios mínimos**: tocar solo lo necesario.
- **Salida por defecto = diff/patch** (no pegar archivos completos), salvo que yo lo pida.
- **Explicación dentro del código**:
  - Docstrings + comentarios por bloque en partes importantes.
  - Evitar comentar lo obvio línea por línea.
- **No releer todo el repo**:
  - Limitarse a rutas/archivos que yo indique.
  - Si falta info: hacer **1 sola pregunta**. Si no es imprescindible, asumir y declararlo.
- Fuera del código: **máximo 3–5 bullets** + comandos exactos.

---

## Arquitectura del módulo (Odoo MVC)

- `models/`
  - `pagos_facturas.py`: lógica core; extiende `account.move` y `res.partner`
  - `topes_afip.py`: topes AFIP; extiende `res.company`
- `views/`: XML (herencias de formularios)
- `controllers/`: mínimo/placeholder
- `security/`: `ir.model.access.csv`
- `static/src/`: assets (placeholder)

Dependencias: `base`, `account`, `delivery`

---

## Lógica de negocio clave (resumen)

- Pagos multi-medio: efectivo + MP + tarjeta en la misma factura.
- Seguimiento de saldo del cliente: `saldo_disponible` (pagos no conciliados).
- Creación automática de pagos/grupos al postear (`action_post()`).
- Validaciones:
  - MP/tarjeta requieren número de transacción (`x_nro_mp`, `x_nro_tarjeta`).
  - `neto_a_pagar` debe quedar en 0 para poder postear.

Campos críticos en `account.move`:
- `x_efectivo`, `x_mp`, `x_tarjeta`
- `x_saldo_a_favor`
- `x_nro_mp`, `x_nro_tarjeta`
- `neto_a_pagar`

AFIP:
- `res.company.x_tope_cf`: tope Consumidor Final (AFIP RG 5700/2025)
- `res.partner.x_no_saldo_favor`: desactiva cálculo de saldo para ciertos clientes

---

## Convenciones

- Campos custom con prefijo `x_`.
- Código y comentarios en español.
- Vistas por herencia con `inherit_id`.

---

## Git (mínimo tokens, máximo práctico)
## Atajo Git para el usuario (1 línea)

Cuando el usuario escriba exactamente:
PUSH "<mensaje>"

Claude debe responder SOLO con comandos bash (sin explicación), ejecutando add+commit+push en:
- repo actual (.)
- repo padre (..)

Reglas:
- Si el mensaje no viene, usar "update".
- Ejecutar ambos repos siempre.
- Si no hay cambios, no fallar: imprimir "No hay cambios..." y seguir.

Plantilla de respuesta (NO modificar el formato):

```bash
git -C . status && git -C . diff --stat
git -C . add -A
git -C . commit -m "<mensaje>" || echo "No hay cambios para commitear en (.)"
git -C . push

git -C .. status && git -C .. diff --stat
git -C .. add -A
git -C .. commit -m "<mensaje>" || echo "No hay cambios para commitear en (..)"
git -C .. push
