redis-cli -n 0 --scan --pattern "queues:data:*" | xargs redis-cli DEL
redis-cli -n 0 --scan --pattern "airport:ramps:*" | xargs redis-cli DEL
redis-cli -n 0 --scan --pattern "airport:runways:*" | xargs redis-cli DEL
redis-cli -n 0 --scan --pattern "airport:service-vehicles:*" | xargs redis-cli DEL
redis-cli -n 0 --scan --pattern "airport:equipment:*" | xargs redis-cli DEL
redis-cli -n 0 --scan --pattern "flights:*" | xargs redis-cli DEL
redis-cli -n 0 --scan --pattern "services:*" | xargs redis-cli DEL
redis-cli -n 0 --scan --pattern "vehicles:*" | xargs redis-cli DEL
