from odoo import models, fields, api
from odoo.exceptions import UserError

class NexaMerchantStores(models.Model):
    _name = 'nexamerchant.stores'
    _description = 'Nexa Merchant Stores'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    api_url = fields.Char(string='API URL', required=True)
    api_key = fields.Char(string='API Key', required=True)
    api_secret = fields.Char(string='API Secret', required=True)
    

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
            self.env['nexamerchant.stores'].create({
                'name': 'New Store',
                'description': 'Description for new store',
                'store_id': 'newstore',
                'merchant_id': self.env['nexamerchant.merchant'].search([], limit=1).id
            })
        return self._transactioning(transaction_logic)