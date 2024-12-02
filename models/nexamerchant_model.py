from odoo import models, fields

class NexaMerchant(models.Model):
    _name = 'nexamerchant.merchant'
    _description = 'Nexa Merchant'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')