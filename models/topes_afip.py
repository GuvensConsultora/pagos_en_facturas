from odoo import models, fields, api
from odoo.exceptions import ValidationError

class TopeConsFinal(models.Model):
    _inherit = 'res.company'
    _description = 'Agregar agregar el campo para establecer el tope de consumidor final'

    x_tope_cf = fields.Float(string="Tope Consumidor Final",help=(
            "Importe máximo que puede facturarse a un Consumidor Final anónimo. "
            "Si la operación supera este monto, el sistema solicitará identificar "
            "al comprador (CUIT/CUIL/DNI) conforme RG 5700/2025."
        ),)
    x_use_pagos_factura = fields.Boolean(
        string="Habilitar Pagos en Facturas",
        default=False,
        help="Activa la sección de pagos directos (efectivo, MP, tarjeta) en las facturas de esta compañía.",
    )

    def _auto_init(self):
        cr = self.env.cr
        cr.execute("SAVEPOINT _ensure_x_use_pagos_factura")
        try:
            cr.execute("""
                ALTER TABLE res_company
                ADD COLUMN IF NOT EXISTS x_use_pagos_factura boolean DEFAULT false
            """)
            cr.execute("RELEASE SAVEPOINT _ensure_x_use_pagos_factura")
        except Exception:
            cr.execute("ROLLBACK TO SAVEPOINT _ensure_x_use_pagos_factura")
        return super()._auto_init()
