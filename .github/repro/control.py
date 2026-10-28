import sys

path = sys.argv[1]
source = open(path).read()
old = "args.planned_start_time = get_datetime(data.planned_start_time)\n"
new = "args.planned_start_time = max(get_datetime(data.planned_start_time), get_datetime(args.from_time))\n"
assert source.count(old) == 1, "control patch anchor not found exactly once"
open(path, "w").write(source.replace(old, new))
print("control patch applied")
