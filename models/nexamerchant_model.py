from odoo import models, fields, api
from odoo.exceptions import UserError

class NexaMerchant(models.Model):
    _name = 'nexamerchant.merchant'
    _description = 'Nexa Merchant'

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
            self.env['nexamerchant.merchant'].create({
                'name': 'New Merchant',
                'description': 'Description for new merchant',
                'api_url': 'https://api.newmerchant.com',
                'api_key': 'newkey',
                'api_secret': 'newsecret'
            })
        return self._transactioning(transaction_logic)