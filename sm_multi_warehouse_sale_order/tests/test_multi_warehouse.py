# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMultiWarehouseSaleOrder(TransactionCase):

    def test_multi_warehouse_split_creates_picking_per_warehouse(self):
        wh1 = self.env.ref('stock.warehouse0')
        wh2 = self.env['stock.warehouse'].create({
            'name': 'MW Test Warehouse 2',
            'code': 'MWT2',
        })
        product = self.env['product.product'].create({
            'name': 'MW Test Product',
            'is_storable': True,
        })
        self.env['stock.quant']._update_available_quantity(
            product, wh1.lot_stock_id, 5)
        self.env['stock.quant']._update_available_quantity(
            product, wh2.lot_stock_id, 5)
        order = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create(
                {'name': 'MW Test Customer'}).id,
            'warehouse_mode': 'multi',
            'order_line': [Command.create({
                'product_id': product.id,
                'product_uom_qty': 8,
                'warehouse_line_ids': [
                    Command.create({'warehouse_id': wh1.id, 'quantity': 5}),
                    Command.create({'warehouse_id': wh2.id, 'quantity': 3}),
                ],
            })],
        })
        order.action_confirm()
        self.assertEqual(len(order.picking_ids), 2)
        qty_by_wh = {
            picking.picking_type_id.warehouse_id:
                sum(picking.move_ids.mapped('product_uom_qty'))
            for picking in order.picking_ids
        }
        self.assertEqual(qty_by_wh.get(wh1), 5)
        self.assertEqual(qty_by_wh.get(wh2), 3)
