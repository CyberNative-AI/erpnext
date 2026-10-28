# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.utils import get_datetime

from erpnext.manufacturing.doctype.operation.test_operation import make_operation
from erpnext.manufacturing.doctype.production_plan.test_production_plan import make_bom
from erpnext.manufacturing.doctype.work_order.test_work_order import make_wo_order_test_record
from erpnext.manufacturing.doctype.workstation.test_workstation import make_workstation
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.tests.utils import ERPNextTestSuite


class TestWorkstationType(ERPNextTestSuite):
	def test_disabled_workstation_not_picked_for_type_only_operation(self):
		workstation_type = create_workstation_type(workstation_type="_Test WT Disabled Pick").name
		disabled = make_workstation(
			workstation_name="_Test WS Disabled Pick Old", workstation_type=workstation_type
		)
		disabled.db_set("disabled", 1)
		active = make_workstation(
			workstation_name="_Test WS Disabled Pick New", workstation_type=workstation_type
		)

		fg_item = make_item("_Test FG Disabled Pick", {"is_stock_item": 1}).name
		rm_item = make_item("_Test RM Disabled Pick", {"is_stock_item": 1}).name
		operation = make_operation(operation="_Test Op Disabled Pick").name
		bom = make_bom(item=fg_item, raw_materials=[rm_item], with_operations=1, do_not_submit=True)
		bom.append(
			"operations",
			{
				"operation": operation,
				"workstation_type": workstation_type,
				"time_in_mins": 60,
				"hour_rate": 100,
			},
		)
		bom.submit()

		work_order = make_wo_order_test_record(item=fg_item, bom_no=bom.name, qty=1)
		workstation = frappe.db.get_value("Job Card", {"work_order": work_order.name}, "workstation")
		self.assertEqual(workstation, active.name)

	@ERPNextTestSuite.change_settings("Manufacturing Settings", {"disable_capacity_planning": 0})
	def test_type_without_enabled_workstation_gives_a_clear_error(self):
		workstation_type = create_workstation_type(workstation_type="_Test WT All Disabled").name
		make_workstation(workstation_name="_Test WS All Disabled", workstation_type=workstation_type).db_set(
			"disabled", 1
		)

		fg_item = make_item("_Test FG All Disabled", {"is_stock_item": 1}).name
		rm_item = make_item("_Test RM All Disabled", {"is_stock_item": 1}).name
		operation = make_operation(operation="_Test Op All Disabled").name
		bom = make_bom(item=fg_item, raw_materials=[rm_item], with_operations=1, do_not_submit=True)
		bom.append(
			"operations",
			{
				"operation": operation,
				"workstation_type": workstation_type,
				"time_in_mins": 60,
				"hour_rate": 100,
			},
		)
		bom.submit()

		self.assertRaisesRegex(
			frappe.ValidationError,
			"has no enabled Workstation",
			make_wo_order_test_record,
			item=fg_item,
			bom_no=bom.name,
			qty=1,
		)

	def test_type_cost_change_reaches_its_workstations(self):
		component = "_Test Component Type Rate"
		if not frappe.db.exists("Workstation Operating Component", component):
			frappe.get_doc(
				{"doctype": "Workstation Operating Component", "component_name": component}
			).insert()

		workstation_type = create_workstation_type(
			workstation_type="_Test WT Rate Change",
			workstation_costs=[{"operating_component": component, "operating_cost": 500}],
		)
		follows_type = make_workstation(
			workstation_name="_Test WS Rate Follows", workstation_type=workstation_type.name
		)
		own_rate = make_workstation(
			workstation_name="_Test WS Rate Own", workstation_type=workstation_type.name
		)
		own_rate.workstation_costs[0].operating_cost = 650
		own_rate.save()

		workstation_type.workstation_costs[0].operating_cost = 800
		workstation_type.save()

		self.assertEqual(frappe.db.get_value("Workstation", follows_type.name, "hour_rate"), 800)
		self.assertEqual(frappe.db.get_value("Workstation", own_rate.name, "hour_rate"), 650)

	@ERPNextTestSuite.change_settings(
		"Manufacturing Settings",
		{"disable_capacity_planning": 0, "allow_overtime": 0, "mins_between_operations": 10},
	)
	def test_type_only_operation_does_not_start_before_previous_operation_ends(self):
		shift = {"start_time": "08:00:00", "end_time": "20:00:00"}
		workstation_type = create_workstation_type(workstation_type="_Test WT Sequence").name
		for name in ("_Test WS Sequence A", "_Test WS Sequence B"):
			workstation = make_workstation(workstation_name=name, workstation_type=workstation_type)
			workstation.append("working_hours", shift)
			workstation.save()

		first_workstation = make_workstation(workstation_name="_Test WS Sequence First")
		first_workstation.append("working_hours", shift)
		first_workstation.save()

		first_operation = make_operation(operation="_Test Op Sequence First").name
		second_operation = make_operation(operation="_Test Op Sequence Second").name
		long_operation = make_operation(operation="_Test Op Sequence Long").name

		# A job of another work order keeps workstation A busy from 08:00 to 12:00.
		long_item = make_item("_Test FG Sequence Long", {"is_stock_item": 1}).name
		long_rm = make_item("_Test RM Sequence Long", {"is_stock_item": 1}).name
		long_bom = make_bom(item=long_item, raw_materials=[long_rm], with_operations=1, do_not_submit=True)
		long_bom.append(
			"operations",
			{
				"operation": long_operation,
				"workstation_type": workstation_type,
				"time_in_mins": 240,
				"hour_rate": 100,
			},
		)
		long_bom.submit()
		make_wo_order_test_record(
			item=long_item, bom_no=long_bom.name, qty=1, planned_start_date="2031-03-05 08:00:00"
		)

		fg_item = make_item("_Test FG Sequence", {"is_stock_item": 1}).name
		rm_item = make_item("_Test RM Sequence", {"is_stock_item": 1}).name
		bom = make_bom(item=fg_item, raw_materials=[rm_item], with_operations=1, do_not_submit=True)
		bom.append(
			"operations",
			{
				"operation": first_operation,
				"workstation": first_workstation.name,
				"time_in_mins": 60,
				"hour_rate": 100,
			},
		)
		bom.append(
			"operations",
			{
				"operation": second_operation,
				"workstation_type": workstation_type,
				"time_in_mins": 60,
				"hour_rate": 100,
			},
		)
		bom.submit()

		work_order = make_wo_order_test_record(
			item=fg_item, bom_no=bom.name, qty=1, planned_start_date="2031-03-05 08:00:00"
		)

		first = frappe.get_doc("Job Card", {"work_order": work_order.name, "operation": first_operation})
		second = frappe.get_doc("Job Card", {"work_order": work_order.name, "operation": second_operation})
		first_end = get_datetime(first.scheduled_time_logs[-1].to_time)
		second_start = get_datetime(second.scheduled_time_logs[0].from_time)

		self.assertGreaterEqual(
			second_start,
			first_end,
			f"{second_operation} is scheduled on {second.workstation} from {second_start}, "
			f"before {first_operation} ends at {first_end}",
		)


def create_workstation_type(**args):
	args = frappe._dict(args)

	if workstation_type := frappe.db.exists("Workstation Type", args.workstation_type):
		return frappe.get_doc("Workstation Type", workstation_type)
	else:
		doc = frappe.new_doc("Workstation Type")
		doc.update(args)
		doc.insert()
		return doc
