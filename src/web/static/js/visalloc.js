fetch("/alloc")
    .then(response => response.json())
    .then(function(dataset) {

        var options = {
            id_div_container: "visavail_container",
            id_div_graph: "visavail_graph",
            line_spacing: 8,
            zoom: {
                enabled: true,
            },
            responsive: {
                enabled: true,
            },

            title: {
                text: "Ramp availability"
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

        var chart = visavail.generate(options, dataset)
    })