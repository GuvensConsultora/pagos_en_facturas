from odoo import models, fields, api
from odoo.exceptions import ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'
    _description = 'Agregar los campos necesarios para registrar los pagos en la misma factura'


    x_efectivo = fields.Float(String="Importe Efectivo")
    x_imp_mp = fields.Float(String="Importe Mercado Pago")
    x_nro_mp = fields.Char(String="Nro. Transacción M.P.")
    x_imp_tarj = fields.Float(String="Importe Tarjeta.")
    x_nro_tarj = fields.Char(String="Nro cupón Tarjeta")
    x_neto = fields.Float(String="Neto a Cancelar",
                          compute='_compute_neto',  #Llamo al metodo de cálculo.
                          store =True, # Almaceno el valor en la base de datos.
                          readonly = True,
                          digits = 'Product Price', # Definimos precisión.
                          tracking = True, # Seguir los cambios en el historial.
)
    # Realizamos el cálculo cuando se actuacilza x_efectivo, x_imp_mp, x_imp_tarj, amount_total, adedudao.
    @api.depends('amount_total', 'x_efectivo', 'x_imp_mp','x_imp_tarj')
    def _compute_neto(self):
        for rec in self:
            rec.x_neto = rec.amount_total - rec.x_efectivo - rec.x_imp_mp - rec.x_imp_tarj


    def action_post(self):
        for record in self:
            # Solo realizamos la validación si el div de pagos debería ser visible
            if record.invoice_payment_term_id.id == 1:
                if record.x_neto != 0:
                    raise ValidationError(
                        "No se puede validar la factura. El 'Neto a Cancelar' (Monto Neto Calculado) debe ser cero."
                        "Por favor, ajuste los pagos (Efectivo, Mercado Pago, Tarjeta) para que el neto sea cero."
                    )
                if record.state != 'posted':  # posteo la factura si no está posteada y evito bucle.
                    res_pos = super().action_post()
                # Cargo en las lineas de documentos la factura que se paga. Ojo por que hay que limpiarlo completo y luego cargar la factura actual solamente.
                lineas_deuda = record.line_ids.filtered(lambda l: l.amount_residual > 0)
                groups_payment = self.env['account.payment.group'].create({
                    'partner_id': record.partner_id.id,        # ID del cliente
                    'partner_type': 'customer',      # o 'supplier'
                    'company_id': self.env.company.id,
                    'currency_id': self.env.company.currency_id.id,
                    'debt_move_line_ids': [(6, 0, lineas_deuda.ids)],
                })
                # Cargar los métodos de pago que están seleccionados en pados en factura. Traer los nro de cupon y operaciones.
                user = self.env.user
                res_user = self.env["res.users"].browse(user.id)
                
                # Buscar diario de efectivo para esta unidad operativa
                journal_efectivo = self.env['account.journal'].search([
                    ('type', '=', 'cash'),
                    ('operating_unit_id', '=', res_user.default_operating_unit_id.id)
                ], limit=1)                

                if not journal_efectivo:
                    raise ValidationError("No se encontró un diario de Efectivo para esta unidad operativa.")
                # Crear el pago si hay efectivo
                if record.x_efectivo > 0 and journal_efectivo:
                    self.env['account.payment'].create({
                        'payment_type': 'inbound',
                        'partner_type': 'customer',
                        'partner_id': record.partner_id.id,
                        'amount': record.x_efectivo,
                        #'payment_method_line_id': self.env.ref('account.account_payment_method_manual_in').id,
                        'journal_id': journal_efectivo.id,
                        'payment_group_id': groups_payment.id,
                    })

                
                # Buscar el diario con code 'mp' y la unidad operativa correspondiente
                journal_mp = self.env['account.journal'].search([('type','=','bank'),
                    ('code', '=', 'MP'),
                    #('operating_unit_id', '=', record.operating_unit_id.id)
                ], limit=1)

                if not journal_mp:
                    raise ValidationError("No se encontró un diario de Mercado Pago. \n Si está creado cambiar el código por MP ")

                                
                # Crear el pago de Mercado Pago
                if record.x_imp_mp > 0:
                    self.env['account.payment'].create({
                        'payment_type': 'inbound',
                        'partner_type': 'customer',
                        'partner_id': record.partner_id.id,
                        'amount': record.x_imp_mp,
                        #'payment_method_line_id': self.env.ref('account.account_payment_method_manual_in').id,  # O uno específico si tenés
                        'journal_id': journal_mp.id,
                        'payment_group_id': groups_payment.id,
                        'ref': f"Nro Transf: {record.x_nro_mp or 'Sin número'}",
                    })


                # Buscar el diario con code 'Tarjetas' y la unidad operativa correspondiente
                journal_tar = self.env['account.journal'].search([('type','=','bank'),
                    ('code', '=', 'TAR'),
                    #('operating_unit_id', '=', record.operating_unit_id.id)
                ], limit=1)

                if not journal_tar:
                    raise ValidationError(f"No se encontró un diario de Tarjetas. \n Si el mismo está creado por favor en el código del diario poner solo TAR")
                
                # Crear el pago de Tarjetas
                if record.x_imp_tarj > 0:
                    self.env['account.payment'].create({
                        'payment_type': 'inbound',
                        'partner_type': 'customer',
                        'partner_id': record.partner_id.id,
                        'amount': record.x_imp_tarj,
                        #'payment_method_line_id': self.env.ref('account.account_payment_method_manual_in').id,  # O uno específico si tenés
                        'journal_id': journal_tar .id,
                        'payment_group_id': groups_payment.id,
                        'ref': f"Nro Transf: {record.x_nro_tarj or 'Sin número'}",
                    })
                # Valido Carga
                groups_payment.post()


    
             ## {'lang': 'es_419', 'tz': 'Europe/Brussels', 'uid': 2, 'allowed_company_ids': [1], 'active_model': 'sale.advance.payment.inv', 'active_id': 5, 'active_ids': [5], 'default_move_type': 'out_invoice', 'default_partner_id': 1115, 'default_partner_shipping_id': 1115, 'default_invoice_payment_term_id': 1, 'default_invoice_origin': 'S00024', 'validate_analytic': True}
  
