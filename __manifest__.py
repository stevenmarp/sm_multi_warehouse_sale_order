# -*- coding: utf-8 -*-
{
    'name': 'Multi Warehouse Sale Order',
    'version': '17.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Choose between three warehouse delivery modes on Sales Orders: standard single warehouse, different warehouse per order line, or split a line quantity across multiple warehouses, with automatic stock suggestions, live free stock validation, and automatic delivery splitting in Odoo 17.',
    'description': """
Multi Warehouse Delivery for Sales Orders in Odoo 17
===================================================

This module extends Odoo's delivery system to allow shipping products in a single Sales Order from different warehouses. It offers three distinct warehouse delivery modes configured per Sales Order:

1. **Sale Order Warehouse**: Standard Odoo behavior where the entire order is delivered from one main warehouse.
2. **Warehouse per Line**: Assign a specific warehouse to each Sales Order line. The system will group lines by warehouse and generate separate delivery orders accordingly.
3. **Multi Warehouse per Line**: Split a single order line quantity across multiple warehouses (e.g., ship 10 units of Product A: 4 from Warehouse SF, 3 from Warehouse LA, and 3 from Warehouse NY).

Key Technical & Functional Features:
------------------------------------

* **Warehouse Delivery Modes**: Configure `warehouse_mode` (order, line, multi) directly on the Sales Order (Other Info tab).
* **Line-Level Warehouse Selection**: Enables selection of `warehouse_id` directly on each Sales Order line.
* **Quantity Allocation Wizard**: A dedicated popup wizard (`fa-list` button) to allocate product quantities across multiple warehouses for a single line, displaying real-time free stock.
* **Automatic Stock Suggestions & Auto-Allocation**:
  - In *Warehouse per Line* mode: If the selected warehouse lacks stock, Odoo automatically recommends and selects the warehouse with the highest available free stock to satisfy the ordered quantity.
  - In *Multi Warehouse per Line* mode: Automatically splits the ordered quantity across warehouses starting from the one with the highest free stock, and falls back to the default warehouse for any remaining balance.
* **Live Free Stock Validation**: Computes and displays real-time free stock (`free_qty`) per warehouse directly in the order lines list and allocation wizards.
* **Strict Quantity Allocation Constraint**: Validates that the sum of allocated quantities matches the ordered quantity exactly before confirming the Sales Order, preventing incomplete allocations or over-allocations.
* **Automatic Split Delivery Orders**: Seamlessly hooks into Odoo's procurement generation (`_create_procurements`) to generate separate delivery transfers (`stock.picking`) grouped by warehouse.
* **Permissions & Security**: Integrates with standard Odoo Multi-Warehouse settings, restricting fields and wizards to authorized users.
* **Seamless Compatibility**: Works with Odoo Community & Enterprise editions, preserving standard inventory reservation and routing logic.
    """,
    'author': 'Steven Marp',
    'website': 'https://apps.odoo.com/apps/modules/browse?author=Steven Marp',
    'license': 'OPL-1',
    'price': 22.00,
    'currency': 'USD',
    'depends': [
        'sale_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
    ],
    'images': [
        'static/description/banner.gif',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
