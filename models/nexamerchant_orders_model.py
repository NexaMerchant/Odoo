from odoo import models, fields, api
from odoo.exceptions import UserError

class NexaMerchantOrders(models.Model):
    _name = 'nexamerchant.orders'
    _description = 'Nexa Merchant Orders'

    name = fields.Char(string='Name', required=True)
    store_id = fields.Char(string='Store ID', required=True)
    description = fields.Text(string='Description')
    total_amount = fields.Float(string='Total Amount', required=True)
    merchant_id = fields.Many2one('nexamerchant.merchant', string='Merchant', required=True)
    order_date = fields.Datetime(string='Order Date')
    order_status = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ], string='Order Status', default='draft')

    @api.model
    def _transactioning(self, func):
        try:
            with self.env.cr.savepoint():
                return func()
        except Exception as e:
            raise UserError(f"Transaction failed: {str(e}")

    def perform_transaction(self):
        def transaction_logic():
            # Your transaction logic here
            self.env['nexamerchant.orders'].create({
                'name': 'New Order',
                'description': 'Description for new order',
                'total_amount': 100.0,
                'merchant_id': self.env['nexamerchant.merchant'].search([], limit=1).id,
                'order_date': fields.Datetime.now(),
                'order_status': 'draft'
            })
        return self._transactioning(transaction_logic)