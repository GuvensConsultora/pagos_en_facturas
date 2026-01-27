# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def _column_exists(cr, table, column):
    cr.execute("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
         LIMIT 1
    """, (table, column))
    return bool(cr.fetchone())

def _sql_type_from_ttype(ttype):
    return {
        "boolean": "boolean",
        "integer": "integer",
        "float": "double precision",
        "monetary": "double precision",
        "char": "varchar",
        "text": "text",
        "date": "date",
        "datetime": "timestamp",
        "many2one": "integer",
    }.get(ttype, "text")

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    field = env["ir.model.fields"].search([
        ("model", "=", "res.partner"),
        ("name", "=", "x_no_saldo_favor"),
    ], limit=1)

    # Si no existe en metadata, no hacemos nada
    if not field:
        return

    # Si la columna ya existe, no hacemos nada
    if _column_exists(cr, "res_partner", "x_no_saldo_favor"):
        return

    # Crear columna según el tipo del campo
    sql_type = _sql_type_from_ttype(field.ttype)
    cr.execute(f'ALTER TABLE res_partner ADD COLUMN x_no_saldo_favor {sql_type}')
