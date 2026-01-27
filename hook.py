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

def post_init_hook(cr, registry):
    # 1) si la columna ya existe, no hacemos nada
    if _column_exists(cr, "res_partner", "x_no_saldo_favor"):
        return

    # 2) (temporal y seguro) crearla como booleano
    #    Si después querés el tipo exacto, lo ajustamos viendo ir.model.fields.
    cr.execute("ALTER TABLE res_partner ADD COLUMN x_no_saldo_favor boolean")
