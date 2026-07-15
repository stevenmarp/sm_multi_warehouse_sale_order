# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    warehouse_mode = fields.Selection(
        selection=[
            ('order', 'Sale Order Warehouse'),
            ('line', 'Warehouse per Line'),
            ('multi', 'Multi Warehouse per Line'),
        ],
        string='Warehouse Mode',
        default='order',
        required=True,
        help="Sale Order Warehouse: all lines are delivered from the order "
             "warehouse.\n"
             "Warehouse per Line: each line can be delivered from its own "
             "warehouse.\n"
             "Multi Warehouse per Line: a line quantity can be split across "
             "several warehouses; one delivery order is created per "
             "warehouse.")

    def action_confirm(self):
        precision = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')
        for order in self.filtered(lambda o: o.warehouse_mode == 'multi'):
            for line in order.order_line:
                if line.product_id.type != 'consu' or not line.warehouse_line_ids:
                    continue
                total = sum(line.warehouse_line_ids.mapped('quantity'))
                if float_compare(total, line.product_uom_qty,
                                 precision_digits=precision) != 0:
                    raise UserError(_(
                        'Product "%(product)s": the warehouse allocation '
                        'total (%(total)s) must equal the ordered quantity '
                        '(%(qty)s).',
                        product=line.product_id.display_name,
                        total=total, qty=line.product_uom_qty))
        return super().action_confirm()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    warehouse_id = fields.Many2one(readonly=False)
    warehouse_line_ids = fields.One2many(
        'sale.order.line.warehouse', 'sale_line_id',
        string='Warehouse Allocations', copy=True)

    def action_open_allocation_wizard(self):
        self.ensure_one()
        view_id = self.env.ref('sm_multi_warehouse_sale_order.view_sale_order_line_allocation_form').id
        return {
            'name': _('Warehouse Allocation'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.line',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view_id, 'form')],
            'target': 'new',
        }

    def _get_free_qty_per_warehouse(self):
        """Free stock of the line product per warehouse, in the line UoM."""
        self.ensure_one()
        warehouses = self.env['stock.warehouse'].search(
            [('company_id', '=', self.order_id.company_id.id)])
        return {
            wh: self.product_id.uom_id._compute_quantity(
                self.product_id.with_context(warehouse_id=wh.id).free_qty,
                self.product_uom)
            for wh in warehouses
        }

    @api.onchange('product_id', 'product_uom_qty')
    def _onchange_suggest_warehouses(self):
        mode = self.order_id.warehouse_mode
        if (mode == 'order' or self.state not in ('draft', 'sent')
                or not self.product_id or self.product_id.type != 'consu'
                or self.product_uom_qty <= 0):
            return
        free = self._get_free_qty_per_warehouse()
        if mode == 'line':
            if free.get(self.warehouse_id, 0.0) >= self.product_uom_qty:
                return
            best = max(free, key=free.get, default=False)
            if best and free[best] >= self.product_uom_qty:
                self.warehouse_id = best
        else:
            remaining = self.product_uom_qty
            commands = [(5, 0, 0)]
            for wh in sorted(free, key=free.get, reverse=True):
                if remaining <= 0:
                    break
                take = min(free[wh], remaining)
                if take <= 0:
                    continue
                commands.append((0, 0,
                    {'warehouse_id': wh.id, 'quantity': take}))
                remaining -= take
            if remaining > 0:
                fallback = self.warehouse_id or self.order_id.warehouse_id
                commands.append((0, 0,
                    {'warehouse_id': fallback.id, 'quantity': remaining}))
            self.warehouse_line_ids = commands

    def _create_procurements(self, product_qty, procurement_uom, origin, values):
        self.ensure_one()
        if self.order_id.warehouse_mode != 'multi' or not self.warehouse_line_ids:
            return super()._create_procurements(
                product_qty, procurement_uom, origin, values)
        procurements = []
        remaining = product_qty
        rounding = procurement_uom.rounding
        for alloc in self.warehouse_line_ids:
            qty = min(self.product_uom._compute_quantity(
                alloc.quantity, procurement_uom), remaining)
            if float_compare(qty, 0.0, precision_rounding=rounding) <= 0:
                continue
            procurements.append(self.env['procurement.group'].Procurement(
                self.product_id, qty, procurement_uom,
                self._get_location_final(), self.product_id.display_name,
                origin, self.order_id.company_id,
                dict(values, warehouse_id=alloc.warehouse_id)))
            remaining -= qty
        if float_compare(remaining, 0.0, precision_rounding=rounding) > 0:
            # ponytail: leftover (qty raised after allocation) ships from the
            # line warehouse instead of blocking the confirmation
            procurements.append(self.env['procurement.group'].Procurement(
                self.product_id, remaining, procurement_uom,
                self._get_location_final(), self.product_id.display_name,
                origin, self.order_id.company_id, values))
        return procurements


class SaleOrderLineWarehouse(models.Model):
    _name = 'sale.order.line.warehouse'
    _description = 'Sale Order Line Warehouse Allocation'

    sale_line_id = fields.Many2one(
        'sale.order.line', string='Sale Order Line', required=True,
        ondelete='cascade', index=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse', required=True)
    quantity = fields.Float(
        string='Quantity', digits='Product Unit of Measure', required=True)
    free_qty = fields.Float(
        string='Free Stock', compute='_compute_free_qty',
        digits='Product Unit of Measure')

    @api.depends('warehouse_id', 'sale_line_id.product_id')
    def _compute_free_qty(self):
        for alloc in self:
            product = alloc.sale_line_id.product_id
            if not product or not alloc.warehouse_id:
                alloc.free_qty = 0.0
                continue
            alloc.free_qty = product.uom_id._compute_quantity(
                product.with_context(
                    warehouse_id=alloc.warehouse_id.id).free_qty,
                alloc.sale_line_id.product_uom)
