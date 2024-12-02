{
    'name': 'Nexa Merchant',
    'version': '1.0',
    'summary': 'A module for managing Nexa Merchants',
    'description': 'This module helps in managing merchants.',
    'author': 'Steve Liu',
    'website': 'https://github.com/NexaMerchant',
    'category': 'Website',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/nexamerchant_view.xml',
        'data/nexamerchant_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}