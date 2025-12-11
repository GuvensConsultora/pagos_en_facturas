from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'
    _description = 'Registro de pagos directos en factura'

    # --- CAMPOS ---
    x_efectivo = fields.Float(string="Importe Efectivo")
    x_imp_mp = fields.Float(string="Importe Mercado Pago")
    x_nro_mp = fields.Char(string="Nro. Transacción M.P.")
    x_imp_tarj = fields.Float(string="Importe Tarjeta")
    x_nro_tarj = fields.Char(string="Nro Cupón Tarjeta")
    
    # Nota del Profesor: store=True en un saldo vivo es delicado. 
    # Si otro usuario paga una factura vieja, este campo NO se enterará automáticamente 
    # hasta que edites esta factura. Para este caso, está bien así.
    x_saldo_favor = fields.Monetary(
        string="Saldo a Favor Disponible",
        compute='_compute_saldo_favor',
        store=True, 
        currency_field='currency_id' # Importante para campos monetarios
    )
    
    x_neto = fields.Monetary(
        string="Neto a Cancelar",
        compute='_compute_neto',
        store=True,
        currency_field='currency_id'
    )

    # --- CONSTRAINS & VALIDACIONES ---
    @api.constrains('x_imp_mp', 'x_nro_mp', 'x_imp_tarj', 'x_nro_tarj')
    def _check_datos_pago(self):
        for record in self:
            if record.x_imp_mp > 0 and not record.x_nro_mp:
                raise ValidationError("Falta el Nro. de Transacción de Mercado Pago.")
            if record.x_imp_tarj > 0 and not record.x_nro_tarj:
                raise ValidationError("Falta el Nro. de Cupón de la Tarjeta.")

    # --- CÁLCULOS (COMPUTE) ---
    @api.depends('amount_total', 'x_efectivo', 'x_imp_mp','x_imp_tarj','x_saldo_favor')
    def _compute_neto(self):
        for rec in self:
            if rec.x_saldo_favor >= rec.amount_total:
                rec.x_neto = 0
            else:
                rec.x_neto = rec.amount_total - rec.x_efectivo - rec.x_imp_mp - rec.x_imp_tarj - rec.x_saldo_favor

    @api.depends('partner_id', 'state', 'amount_total')        
    def _compute_saldo_favor(self):
        """
        Calcula el saldo a favor (créditos no aplicados) del cliente.
        """
        for rec in self:
            if not rec.partner_id:
                rec.x_saldo_favor = 0.0
                continue

            # 1. Definir Dominio (Tu lógica optimizada)
            domain = [
                ('partner_id', '=', rec.partner_id.id),
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('account_id.account_type', '=', 'asset_receivable'), # Solo cuentas a cobrar
                ('amount_residual', '!=', 0) # Todo lo que no esté conciliado
            ]

            # 2. Consulta SQL Rápida
            resultado = self.env['account.move.line'].read_group(
                domain=domain,
                fields=['amount_residual'], 
                groupby=['partner_id']
            )

            # 3. Asignación Segura (Evitamos el IndexError)
            saldo = resultado[0]['amount_residual'] if resultado else 0.0
            
            # 4. Guardamos en positivo (abs) para visualización
            rec.x_saldo_favor = abs(saldo)

    # --- ONCHANGE (Para feedback inmediato en UI) ---
    @api.onchange('partner_id')
    def _onchange_partner_update_saldo(self):
        # Al cambiar el partner, forzamos el recálculo visualmente
        self._compute_saldo_favor()
            
    def action_post(self):
        for record in self:
            # Solo realizamos la validación si el div de pagos debería ser visible
            if record.invoice_payment_term_id.id == 1:  #Verificamos que sea pago inmediato
                if record.x_saldo_favor >= record.x_neto:
                    raise UserError(f" Saldo a favor {record.x_saldo_favor} Neto: {record.x_neto|")
                    # posteo la factura si no está posteada y evito bucle.
                    if record.state != 'posted':  
                        res_pos = super().action_post()
                        
                if record.x_neto != 0:  # Si el neto a pargar es diferente a cero bloquea
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
                #raise ValidationError(f"La unidad operativos {res_user.default_operating_unit_id.id} ")
                if not journal_efectivo:
                    raise ValidationError("No se encontró un diario de Efectivo para esta unidad operativa, o el código está mal escrito el mismo tiene que ser cash")
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
                    ('code', 'ilike', '%MP%'),
                    ('operating_unit_id', '=', record.operating_unit_id.id)
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
                    ('code', 'ilike', '%TAR%'),
                    ('operating_unit_id', '=', record.operating_unit_id.id)
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
                # Valido el payment group
                groups_payment.post()

            else:
                # posteo la factura si no está posteada y evito bucle.
                if record.state != 'posted':  
                    res_pos = super().action_post()

    
            
            
#              ## {'lang': 'es_419', 'tz': 'Europe/Brussels', 'uid': 2, 'allowed_company_ids': [1], 'active_model': 'sale.advance.payment.inv', 'active_id': 5, 'active_ids': [5], 'default_move_type': 'out_invoice', 'default_partner_id': 1115, 'default_partner_shipping_id': 1115, 'default_invoice_payment_term_id': 1, 'default_invoice_origin': 'S00024', 'validate_analytic': True}
  
