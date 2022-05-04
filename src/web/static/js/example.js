var gantt
var tasks

fetch("/alloc")
    .then(response => response.json())
    .then(function(data) {

        let taskStatus = {
            "none": "bar",
            "one": "bar-failed",
            "two": "bar-running",
            "three": "bar-killed"
        };

        taskStatusValues = Object.keys(taskStatus)

        taskNames = data.Sections

        data.Items.forEach(function(i) {
            i.startDate = moment(i.startDate).toDate()
            i.endDate = moment(i.endDate).toDate()
        })
        tasks = data.Items

        console.log(data)

        tasks.sort(function(a, b) {
            return a.endDate - b.endDate;
        });
        let maxDate = tasks[tasks.length - 1].endDate;
        tasks.sort(function(a, b) {
            return a.startDate - b.startDate;
        });
        let minDate = tasks[0].startDate;

        let format = "%H:%M";
        let timeDomainString = "1week";

        gantt = d3.gantt(tasks).taskTypes(taskNames).taskStatus(taskStatus).tickFormat(format);

        gantt.timeDomainMode("fixed");
        changeTimeDomain(timeDomainString);

        gantt(tasks);
    })

function changeTimeDomain(timeDomainString) {
    function getEndDate() {
        let lastEndDate = Date.now();
        if (tasks.length > 0) {
            lastEndDate = tasks[tasks.length - 1].endDate;
        }

        return lastEndDate;
    }
    this.timeDomainString = timeDomainString;
    switch (timeDomainString) {
        case "1hr":
            format = "%H:%M:%S";
            gantt.timeDomain([d3.timeHour.offset(getEndDate(), -1), getEndDate()]);
            break;
        case "3hr":
            format = "%H:%M";
            gantt.timeDomain([d3.timeHour.offset(getEndDate(), -3), getEndDate()]);
            break;

        case "6hr":
            format = "%H:%M";
            gantt.timeDomain([d3.timeHour.offset(getEndDate(), -6), getEndDate()]);
            break;

        case "1day":
            format = "%H:%M";
            gantt.timeDomain([d3.timeDay.offset(getEndDate(), -1), getEndDate()]);
            break;

        case "1week":
            format = "%a %H:%M";
            gantt.timeDomain([d3.timeDay.offset(getEndDate(), -7), getEndDate()]);
            break;
        default:
            format = "%H:%M"

    }
    gantt.tickFormat(format);
    gantt.redraw(tasks);
}