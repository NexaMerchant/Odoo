from odoo import models, fields, api
from odoo.exceptions import UserError

class NexaMerchantProducts(models.Model):
    _name = 'nexamerchant.products'
    _description = 'Nexa Merchant Products'

    name = fields.Char(string='Name', required=True)
    store_id = fields.Char(string='Store ID', required=True)
    description = fields.Text(string='Description')
    price = fields.Float(string='Price', required=True)
    merchant_id = fields.Many2one('nexamerchant.merchant', string='Merchant', required=True)
    product_image = fields.Binary(string='Product Image')

    @api.model
    def _transactioning(self, func):
        try:
            with self.env.cr.savepoint():
                return func()
        except Exception as e:
            raise UserError(f"Transaction failed: {str(e)}")

    def perform_transaction(self):
        def transaction_logic():
            # Your transaction logic here
            self.env['nexamerchant.products'].create({
                'name': 'New Product',
                'description': 'Description for new product',
                'price': 100.0,
                'merchant_id': self.env['nexamerchant.merchant'].search([], limit=1).id,
                'product_image': None
            })
        return self._transactioning(transaction_logic)