function show_allocations(resource, api_key) {
    // console.log("show_allocations", resource, api_key)

    fetch("/airport/allocation/"+resource, {headers: new Headers({"api-key": api_key})})

        .then(response => response.json())

        .then(function(dataset) {

            // console.log(dataset)
            let options = {
                id_div_graph: "visavail_graph",
                id_div_container: "visavail_container",
                line_spacing: 8,
                zoom: {
                    enabled: true,
                },
                responsive: {
                    enabled: true,
                },

                title: {
                    text: resource.slice(0, resource.length - 1) + " availability"
                },

                legend: {
                    enabled: false
                },

                icon: {
                    class_has_data: 'fas fa-fw fa-check',
                    class_has_no_data: 'fas fa-fw fa-exclamation-circle'
                },
                date_in_utc: true,
                date_plus_time: true
            };

            let chart = visavail.generate(options, dataset);
        })
}