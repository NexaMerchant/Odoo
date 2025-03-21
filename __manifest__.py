{
    'name': 'Nexa Merchant',
    'version': '1.0',
    'summary': 'A module for managing Nexa Merchants',
    'description': 'This module helps in managing merchants.',
    'author': 'Steve Liu',
    'website': 'https://github.com/NexaMerchant',
    'category': 'Website',
    "depends": ["base", "web"],
    'data': [
        'security/ir.model.access.csv',
    ],

    "post_load": None,
    "pre_init_hook": None,
    "post_init_hook": None,
    "uninstall_hook": None,

    'installable': True,
    'application': True,
    'auto_install': False,
}