{
    'name': "pagos_en_facturas",
    'version': '17.0',
    'category': 'Custom',
    'depends': ['base','account','delivery'],
    'data': ['views/view.xml',
             'security/ir.model.access.csv',
             'views/res_partner_view.xml',
             ],
    'post_init_hook':'post_init_hook'

    'assets': {
        'web.assets_frontend': [
            'pagos_en_facturas/static/src/js/main.js',
            'pagos_en_facturas/static/src/css/style.css',
        ],
    },
    'installable': True,
    'application': True,
}
