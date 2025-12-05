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
                rec.x_neto = rec.amount_total - rec.x_efectivo - rec.x_imp_mp - rec.x_imp_tarj - rec.saldo_favor

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

    # --- LOGICA DE POSTEO (El núcleo duro) ---
    def action_post(self):
        # Buscamos la referencia del término de pago de forma segura
        # TIP: Ve a Ajustes -> Técnico -> Identificadores Externos y busca el de "Pago Inmediato"
        # Usualmente es 'account.account_payment_term_immediate'
        pago_inmediato = self.env.ref('account.account_payment_term_immediate', raise_if_not_found=False)
        
        for record in self:
            # 1. Validación de Término de Pago (Sin hardcodear ID 1)
            es_contado = pago_inmediato and record.invoice_payment_term_id.id == pago_inmediato.id
            
            # Si no es contado, seguimos con el flujo normal
            if not es_contado:
                if record.state != 'posted':
                    super(AccountMove, record).action_post()
                continue # Pasamos al siguiente registro

            # 2. Si ES contado, validamos montos
            # Usamos float_compare para evitar errores de redondeo (0.00000001 != 0)
            from odoo.tools import float_is_zero
            if not float_is_zero(record.x_neto, precision_digits=2):
                 raise ValidationError(
                    f"Para validar con Pago Inmediato, el 'Neto a Cancelar' debe ser 0. \n"
                    f"Falta cubrir: {record.x_neto}"
                )

            # 3. Posteo Original (Primero confirmamos la factura para generar deuda)
            if record.state != 'posted':
                super(AccountMove, record).action_post()

            # 4. Lógica de Pagos
            # Solo si hay algo que pagar (x_efectivo, mp o tarjeta > 0)
            if record.x_efectivo == 0 and record.x_imp_mp == 0 and record.x_imp_tarj == 0:
                continue

            # Creamos el Payment Group (ADHOC)
            # Buscamos las líneas de deuda de ESTA factura recién creada
            lineas_deuda = record.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
            )
            
            groups_payment = self.env['account.payment.group'].create({
                'partner_id': record.partner_id.id,
                'company_id': record.company_id.id, # Mejor usar record.company_id
                'debt_move_line_ids': [(6, 0, lineas_deuda.ids)],
            })

            # Helper para crear pagos y evitar repetir código
            def crear_pago(monto, diario_code, ref_pago=""):
                if monto <= 0: return
                
                # Búsqueda segura de diario por código y compañía
                journal = self.env['account.journal'].search([
                    ('type', 'in', ('cash', 'bank')),
                    ('code', '=', diario_code), # Busca exacto, evita el ilike peligroso
                    ('company_id', '=', record.company_id.id)
                ], limit=1)

                if not journal:
                     raise ValidationError(f"No se encontró el diario con código '{diario_code}' en la compañía actual.")

                self.env['account.payment'].create({
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': record.partner_id.id,
                    'amount': monto,
                    'journal_id': journal.id,
                    'payment_group_id': groups_payment.id,
                    'ref': ref_pago,
                })

            # Creamos los pagos individuales
            # Asegúrate que los códigos 'CSH', 'MP', 'TAR' coincidan con tus diarios
            crear_pago(record.x_efectivo, 'CSH1', 'Efectivo en Caja') # Ajusta 'CSH1' a tu código real de caja
            crear_pago(record.x_imp_mp, 'MP', f"MP: {record.x_nro_mp}")
            crear_pago(record.x_imp_tarj, 'TAR', f"Cupón: {record.x_nro_tarj}")

            # 5. Confirmamos el grupo de pagos (Esto concilia automáticamente)
            groups_payment.post()
            
        return True





















# from odoo import models, fields, api
# from odoo.exceptions import ValidationError, UserError
# import logging

# _logger = logging.getLogger(__name__)



# class AccountMove(models.Model):
#     _inherit = 'account.move'
#     _description = 'Agregar los campos necesarios para registrar los pagos en la misma factura'


#     x_efectivo = fields.Float(String="Importe Efectivo")
#     x_imp_mp = fields.Float(String="Importe Mercado Pago")
#     x_nro_mp = fields.Char(String="Nro. Transacción M.P.")
#     x_imp_tarj = fields.Float(String="Importe Tarjeta.")
#     x_nro_tarj = fields.Char(String="Nro cupón Tarjeta")
#     x_saldo_favor = fields.Float(String="Saldo a Favor",
#                                  compute='_compute_saldo_favor',
#                                  store=True, # Alamaceno el valor en la base de datos.
#                                  readonly = True, # Solo lectura. 
#                                  digits = 'Product Price', # Deinimos la precisión ... seguramente hay otros modelos.
#                                  tracking = True, # Sigo las pistas en el chater.
#                                 )
#     x_neto = fields.Float(String="Neto a Cancelar",
#                           compute='_compute_neto',  #Llamo al metodo de cálculo.
#                           store =True, # Almaceno el valor en la base de datos.
#                           readonly = True,
#                           digits = 'Product Price', # Definimos precisión.
#                           tracking = True, # Seguir los cambios en el historial.
#                         )


#     @api.constrains('x_imp_mp', 'x_nro_mp', 'x_imp_tarj', 'x_nro_tarj')
#     def _check_datos_pago(self):
#         for record in self:
#             if record.x_imp_mp > 0 and not record.x_nro_mp:
#                 raise ValidationError("Debe ingresar el número de transacción de Mercado Pago.")
#             if record.x_imp_tarj > 0 and not record.x_nro_tarj:
#                 raise ValidationError("Debe ingresar el número de cupón de la Tarjeta.")

    
#     # Realizamos el cálculo cuando se actuacilza x_efectivo, x_imp_mp, x_imp_tarj, amount_total, adedudao.

#     @api.depends('amount_total', 'x_efectivo', 'x_imp_mp','x_imp_tarj')
#     def _compute_neto(self):
#         for rec in self:   
#             rec.x_neto = rec.amount_total - rec.x_efectivo - rec.x_imp_mp - rec.x_imp_tarj

#     @api.onchange('partner_id')        
#     def _compute_saldo_favor(self):
#         for rec in self:
#             rec.x_saldo_favor = self._recalc_x_saldo_favor()

    
# ###################################################
#     # Revisamos los valores residuales de los pagos para determinar saldo a favor

#     def _is_immediate_payment_term(self):

#         """Lee el término de la factura y loguea si coincide con 'Pago inmediato'."""
#         PayTerm = self.env['account.payment.term']
#         # A) Intento por XML-ID (si existe en tu base)
#         pt_immediate = self.env.ref('account.account_payment_term_immediate', raise_if_not_found=False)
#         # B) Fallback por nombre exacto (ajusta si tu nombre difiere)
#         if not pt_immediate:
#             pt_immediate = PayTerm.search([('name', '=', 'Pago inmediato')], limit=1)

#         for inv in self:
#             term = inv.invoice_payment_term_id
#             if not term:
#                 _logger.info("Factura %s sin término de pago.", inv.id)
#                 continue
#             if not pt_immediate:
#                 _logger.warning("No encuentro el término 'Pago inmediato' (ni por XML-ID ni por nombre).")
#                 continue

#             if term.id == pt_immediate.id:
#                 _logger.info("OK: Factura %s usa 'Pago inmediato' (term_id=%s).", inv.id, term.id)
#             else:
#                 _logger.info("NO: Factura %s usa otro término (term_id=%s, esperado=%s).",
#                              inv.id, term.id, pt_immediate.id)
    
#     # def _ou_credit_available(self):
#     #     """Suma créditos (líneas a cobrar negativas y no conciliadas) en misma OU."""
#     #     self.ensure_one()
#     #     domain = [
#     #         ('partner_id', '=', self.partner_id.id),
#     #         ('account_id.account_type', '=', 'receivable'),
#     #         ('reconciled', '=', False),
#     #         ('balance', '<', 0),                 # crédito
#     #         ('move_id.state', '=', 'posted'),
#     #     ]
#     #     # (supuesto) OCA operating_unit instalado
#     #     if 'operating_unit_id' in self._fields and self.operating_unit_id:
#     #         domain.append(('operating_unit_id', '=', self.operating_unit_id.id))
#     #     lines = self.env['account.move.line'].search(domain)
#     #     # balance es negativo → crédito positivo
#     #     return sum(-l.balance for l in lines)

#     def _recalc_x_saldo_favor(self):  # Recalculo el saldo\
#         for rec in self:
#             domain = [
#                 ('partner_id', '=', rec.partner_id.id),
#         ('parent_state', '=', 'posted'),      # Solo asientos confirmados
#                 ('reconciled', '=', False),           # <--- EL GRAN FILTRO (Solo lo abierto)
#                 ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
#                 ('amount_residual', '!=', 0)          # Evitar basura técnica con residual 0
#             ]


#             resultado = self.env['account.move.line'].read_group(
#                 domain=domain,
#                 fields=['amount_residual'], 
#                 groupby=['partner_id']
#             )


#             # Si 'resultado' tiene datos, dame el valor. Si no (lista vacía), devuelve 0.0
#             return resultado[0]['amount_residual'] if resultado else 0.0
            
#             #raise UserError (f"Cantidades {len(self)}. Nombre {rec.partner_id.id} Dominio {domain} Resultado {resultado[0]['amount_residual']}")
#         # for inv in self.filtered(lambda m: m.move_type == 'out_invoice'):
#         #     if inv._is_immediate_payment_term():
#         #         credito = inv._ou_credit_available()
#         #         raise UserError(f" linea 98 Credito: {credito}")
#         #         inv.x_saldo_favor = min(credito, inv.amount_total or 0.0)
#         #     else:
#         #         inv.x_saldo_favor = 0.0

#     @api.model
#     def create(self, vals):
#         moves = super().create(vals)   # admite dict o lista
#         moves._recalc_x_saldo_favor()  # ← “en el momento” de crear
#         return moves

#     def write(self, vals):
#         res = super().write(vals)
#         # Recalcular si cambian partner/OU/pt/total
#         watched = {'partner_id', 'operating_unit_id', 'invoice_payment_term_id', 'invoice_line_ids'}
#         if watched & set(vals.keys()):
#             self._recalc_x_saldo_favor()
#         return res

#     @api.onchange('partner_id', 'operating_unit_id', 'invoice_payment_term_id', 'invoice_line_ids')
#     def _onchange_recalc_saldo(self):
#         # feedback inmediato en UI (draft)
#         self._recalc_x_saldo_favor()
        
            
#     def action_post(self):
#         for record in self:
#             # Verificamos el monto total de la factura y evaluamos si hay que identificar el C.F.A.
#             #vat = self.env['res.partner'].browse(record.partner_id.id).vat
#             #if record.amount_total >= self.env.company.x_tope_cf and not vat :
#             #    raise ValidationError("Este comprobante supera el importe establecido para no identificar al Consumidor Final. Por favor cree el contacto identificandolo completamente con su nro de cuil cuit o dni. O modifique el tope establecido en la compañía.")
            
#             # Solo realizamos la validación si el div de pagos debería ser visible
#             if record.invoice_payment_term_id.id == 1:
#                 if record.x_neto != 0:
#                     raise ValidationError(
#                         "No se puede validar la factura. El 'Neto a Cancelar' (Monto Neto Calculado) debe ser cero."
#                         "Por favor, ajuste los pagos (Efectivo, Mercado Pago, Tarjeta) para que el neto sea cero."
#                     )
#                 if record.state != 'posted':  # posteo la factura si no está posteada y evito bucle.
#                     res_pos = super().action_post()
#                 # Cargo en las lineas de documentos la factura que se paga. Ojo por que hay que limpiarlo completo y luego cargar la factura actual solamente.
#                 lineas_deuda = record.line_ids.filtered(lambda l: l.amount_residual > 0)
#                 groups_payment = self.env['account.payment.group'].create({
#                     'partner_id': record.partner_id.id,        # ID del cliente
#                     'partner_type': 'customer',      # o 'supplier'
#                     'company_id': self.env.company.id,
#                     'currency_id': self.env.company.currency_id.id,
#                     'debt_move_line_ids': [(6, 0, lineas_deuda.ids)],
#                 })
#                 # Cargar los métodos de pago que están seleccionados en pados en factura. Traer los nro de cupon y operaciones.
#                 user = self.env.user
#                 res_user = self.env["res.users"].browse(user.id)
                
#                 # Buscar diario de efectivo para esta unidad operativa
#                 journal_efectivo = self.env['account.journal'].search([
#                     ('type', '=', 'cash'),
#                     ('operating_unit_id', '=', res_user.default_operating_unit_id.id)
#                 ], limit=1)                
#                 #raise ValidationError(f"La unidad operativos {res_user.default_operating_unit_id.id} ")
#                 if not journal_efectivo:
#                     raise ValidationError("No se encontró un diario de Efectivo para esta unidad operativa, o el código está mal escrito el mismo tiene que ser cash")
#                 # Crear el pago si hay efectivo
#                 if record.x_efectivo > 0 and journal_efectivo:
#                     self.env['account.payment'].create({
#                         'payment_type': 'inbound',
#                         'partner_type': 'customer',
#                         'partner_id': record.partner_id.id,
#                         'amount': record.x_efectivo,
#                         #'payment_method_line_id': self.env.ref('account.account_payment_method_manual_in').id,
#                         'journal_id': journal_efectivo.id,
#                         'payment_group_id': groups_payment.id,
#                     })

                
#                 # Buscar el diario con code 'mp' y la unidad operativa correspondiente
#                 journal_mp = self.env['account.journal'].search([('type','=','bank'),
#                     ('code', 'ilike', '%MP%'),
#                     ('operating_unit_id', '=', record.operating_unit_id.id)
#                 ], limit=1)
                
#                 if not journal_mp:
#                     raise ValidationError("No se encontró un diario de Mercado Pago. \n Si está creado cambiar el código por MP ")
                
#                 # Crear el pago de Mercado Pago
#                 if record.x_imp_mp > 0:
#                     self.env['account.payment'].create({
#                         'payment_type': 'inbound',
#                         'partner_type': 'customer',
#                         'partner_id': record.partner_id.id,
#                         'amount': record.x_imp_mp,
#                         #'payment_method_line_id': self.env.ref('account.account_payment_method_manual_in').id,  # O uno específico si tenés
#                         'journal_id': journal_mp.id,
#                         'payment_group_id': groups_payment.id,
#                         'ref': f"Nro Transf: {record.x_nro_mp or 'Sin número'}",
#                     })

#                 # Buscar el diario con code 'Tarjetas' y la unidad operativa correspondiente
#                 journal_tar = self.env['account.journal'].search([('type','=','bank'),
#                     ('code', 'ilike', '%TAR%'),
#                     ('operating_unit_id', '=', record.operating_unit_id.id)
#                 ], limit=1)

#                 if not journal_tar:
#                     raise ValidationError(f"No se encontró un diario de Tarjetas. \n Si el mismo está creado por favor en el código del diario poner solo TAR")
                
#                 # Crear el pago de Tarjetas
#                 if record.x_imp_tarj > 0:
#                     self.env['account.payment'].create({
#                         'payment_type': 'inbound',
#                         'partner_type': 'customer',
#                         'partner_id': record.partner_id.id,
#                         'amount': record.x_imp_tarj,
#                         #'payment_method_line_id': self.env.ref('account.account_payment_method_manual_in').id,  # O uno específico si tenés
#                         'journal_id': journal_tar .id,
#                         'payment_group_id': groups_payment.id,
#                         'ref': f"Nro Transf: {record.x_nro_tarj or 'Sin número'}",
#                     })
#                 # Valido el payment group
#                 groups_payment.post()

#             else:
#                 # posteo la factura si no está posteada y evito bucle.
#                 if record.state != 'posted':  
#                     res_pos = super().action_post()

    
            
            
#              ## {'lang': 'es_419', 'tz': 'Europe/Brussels', 'uid': 2, 'allowed_company_ids': [1], 'active_model': 'sale.advance.payment.inv', 'active_id': 5, 'active_ids': [5], 'default_move_type': 'out_invoice', 'default_partner_id': 1115, 'default_partner_shipping_id': 1115, 'default_invoice_payment_term_id': 1, 'default_invoice_origin': 'S00024', 'validate_analytic': True}
  
