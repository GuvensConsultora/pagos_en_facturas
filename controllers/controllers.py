# -*- coding: utf-8 -*-
from odoo import http

class Guvens(http.Controller):
    @http.route('/pagos_en_facturas', auth='public')
    def index(self, **kw):
        return "Hello from pagos_en_facturas!"