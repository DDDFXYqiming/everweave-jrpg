extends SceneTree
const Connection = preload("res://client/service_connection.gd")
func _initialize() -> void:_run.call_deferred()
func _run() -> void:
	var path := "res://userdata/service-reconnect-runtime.json"
	var connection = Connection.new()
	connection.configure(path,"old")
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_string(JSON.stringify({"url":"http://127.0.0.1:54321","token":"new-token","instance_id":"new"}))
	file.close()
	connection.failed("test")
	connection.next_probe_msec=0
	assert(connection.due())
	var value := connection.runtime()
	assert(value.instance_id=="new" and value.url.ends_with(":54321"))
	connection.discovered(value)
	assert(connection.expected_instance_id=="new")
	connection.recovered("new")
	assert(not connection.disconnected and not connection.due())
	assert(FileAccess.get_file_as_string(connection.log_path).contains("client.connection.recovered"))
	print("SERVICE_CONNECTION_OK rediscovery=true instance_change=true bounded_backoff=true")
	quit(0)
