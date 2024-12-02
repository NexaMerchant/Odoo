from odoo import models, fields

class NexaMerchant(models.Model):
    _name = 'nexamerchant.merchant'
    _description = 'Nexa Merchant'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    api_url = fields.Char(string='API URL', required=True)
    api_key = fields.Char(string='API Key', required=True)
    api_secret = fields.Char(string='API Secret', required=True)