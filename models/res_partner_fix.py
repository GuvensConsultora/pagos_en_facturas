# -*- coding: utf-8 -*-
from odoo import models

class ResPartner(models.Model):
    _inherit = "res.partner"

    def init(self):
        # Esto corre al inicializar el registry. Usamos SQL directo para arreglar la DB.
        self._cr.execute("""
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'res_partner'
               AND column_name = 'x_no_saldo_favor'
             LIMIT 1
        """)
        exists = bool(self._cr.fetchone())
        if not exists:
            # Tipo temporal: boolean. (Luego lo ajustás si el campo real era otro tipo)
            self._cr.execute("ALTER TABLE res_partner ADD COLUMN x_no_saldo_favor boolean")
