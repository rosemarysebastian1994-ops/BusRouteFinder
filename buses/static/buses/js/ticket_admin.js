document.addEventListener('DOMContentLoaded', function () {

    const scheduleField =
        document.getElementById('id_schedule');

    const sourceField =
        document.getElementById('id_source_stop');

    const destinationField =
        document.getElementById('id_destination_stop');


    if (
        !scheduleField ||
        !sourceField ||
        !destinationField
    ) {
        return;
    }


    function loadStops(scheduleId) {

        sourceField.innerHTML = '';
        destinationField.innerHTML = '';


        const emptySource =
            new Option(
                '---------',
                ''
            );

        const emptyDestination =
            new Option(
                '---------',
                ''
            );


        sourceField.appendChild(
            emptySource
        );

        destinationField.appendChild(
            emptyDestination
        );


        if (!scheduleId) {
            return;
        }


        fetch(
            `/buses/ajax/schedule-stops/?schedule_id=${scheduleId}`,
            {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            }
        )
        .then(response => {

            if (!response.ok) {
                throw new Error(
                    'Failed to load stops.'
                );
            }

            return response.json();
        })
        .then(data => {

            if (!data.success) {
                return;
            }


            data.stops.forEach(stop => {

                const sourceOption =
                    new Option(
                        `${stop.order}. ${stop.name}`,
                        stop.id
                    );

                const destinationOption =
                    new Option(
                        `${stop.order}. ${stop.name}`,
                        stop.id
                    );


                sourceField.appendChild(
                    sourceOption
                );

                destinationField.appendChild(
                    destinationOption
                );

            });

        })
        .catch(error => {

            console.error(
                'Error loading route stops:',
                error
            );

        });

    }


    scheduleField.addEventListener(
        'change',
        function () {

            loadStops(
                this.value
            );

        }
    );


    /*
     * Load stops when editing an
     * existing ticket.
     */
    if (scheduleField.value) {

        const currentSource =
            sourceField.value;

        const currentDestination =
            destinationField.value;


        loadStops(
            scheduleField.value
        );


        setTimeout(function () {

            sourceField.value =
                currentSource;

            destinationField.value =
                currentDestination;

        }, 300);

    }

});