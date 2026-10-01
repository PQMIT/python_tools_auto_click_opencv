from dumpsys_parser import dump_activity_top, parse_view_hierarchy, find_by_class, find_by_resid

nodes = parse_view_hierarchy(dump_activity_top())

# Tìm theo class, ví dụ tất cả EditText đang hiển thị
edit_texts = find_by_class(nodes, "EditText")

# Tìm theo resource-id, ví dụ chứa "submit"
submit_nodes = find_by_resid(nodes, "com.shopee.vn.dfpluginshopee7:id/tv_state_btn")