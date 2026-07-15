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

    @property
    def _product_uom(self):
        return self.product_uom_id if 'product_uom_id' in self._fields else self.product_uom

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
                self._product_uom)
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
            commands = [fields.Command.clear()]
            for wh in sorted(free, key=free.get, reverse=True):
                if remaining <= 0:
                    break
                take = min(free[wh], remaining)
                if take <= 0:
                    continue
                commands.append(fields.Command.create(
                    {'warehouse_id': wh.id, 'quantity': take}))
                remaining -= take
            if remaining > 0:
                fallback = self.warehouse_id or self.order_id.warehouse_id
                commands.append(fields.Command.create(
                    {'warehouse_id': fallback.id, 'quantity': remaining}))
            self.warehouse_line_ids = commands

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        multi_lines = self.filtered(lambda l: l.order_id.warehouse_mode == 'multi' and l.warehouse_line_ids)
        other_lines = self - multi_lines
        
        res = True
        if other_lines:
            res = super(SaleOrderLine, other_lines)._action_launch_stock_rule(previous_product_uom_qty)
            
        if multi_lines:
            if self._context.get("skip_procurement"):
                return True
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            procurements = []
            for line in multi_lines:
                line = line.with_company(line.company_id)
                if line.state != 'sale' or not line.product_id.type in ('consu', 'product'):
                    continue
                qty = line._get_qty_procurement(previous_product_uom_qty)
                if float_compare(qty, line.product_uom_qty, precision_digits=precision) == 0:
                    continue

                group_id = line._get_procurement_group()
                if not group_id:
                    group_id = self.env['procurement.group'].create(line._prepare_procurement_group_vals())
                    line.order_id.procurement_group_id = group_id
                else:
                    updated_vals = {}
                    if group_id.partner_id != line.order_id.partner_shipping_id:
                        updated_vals.update({'partner_id': line.order_id.partner_shipping_id.id})
                    if group_id.move_type != line.order_id.picking_policy:
                        updated_vals.update({'move_type': line.order_id.picking_policy})
                    if updated_vals:
                        group_id.write(updated_vals)

                values = line._prepare_procurement_values(group_id=group_id)
                product_qty = line.product_uom_qty - qty

                line_uom = line._product_uom
                quant_uom = line.product_id.uom_id
                product_qty, procurement_uom = line_uom._adjust_uom_quantities(product_qty, quant_uom)
                
                remaining = product_qty
                rounding = procurement_uom.rounding
                
                for alloc in line.warehouse_line_ids:
                    alloc_qty = min(line_uom._compute_quantity(
                        alloc.quantity, procurement_uom), remaining)
                    if float_compare(alloc_qty, 0.0, precision_rounding=rounding) <= 0:
                        continue
                    procurements.append(self.env['procurement.group'].Procurement(
                        line.product_id, alloc_qty, procurement_uom,
                        line.order_id.partner_shipping_id.property_stock_customer,
                        line.product_id.display_name, line.order_id.name,
                        line.order_id.company_id,
                        dict(values, warehouse_id=alloc.warehouse_id)))
                    remaining -= alloc_qty
                if float_compare(remaining, 0.0, precision_rounding=rounding) > 0:
                    procurements.append(self.env['procurement.group'].Procurement(
                        line.product_id, remaining, procurement_uom,
                        line.order_id.partner_shipping_id.property_stock_customer,
                        line.product_id.display_name, line.order_id.name,
                        line.order_id.company_id, values))
            if procurements:
                procurement_group = self.env['procurement.group']
                if self.env.context.get('import_file'):
                    procurement_group = procurement_group.with_context(import_file=False)
                procurement_group.run(procurements)

            orders = multi_lines.mapped('order_id')
            for order in orders:
                pickings_to_confirm = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
                if pickings_to_confirm:
                    pickings_to_confirm.action_confirm()
        return res


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
                alloc.sale_line_id._product_uom)
