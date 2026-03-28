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
