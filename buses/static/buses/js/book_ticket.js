console.log(
    'BOOK TICKET JAVASCRIPT LOADED'
);

document.addEventListener(
    'DOMContentLoaded',
    function () {

        const scheduleField =
            document.getElementById(
                'id_schedule'
            );

        const sourceField =
            document.getElementById(
                'id_source_stop'
            );

        const destinationField =
            document.getElementById(
                'id_destination_stop'
            );

        const passengerCountField =
            document.getElementById(
                'id_passenger_count'
            );

        const fareSection =
            document.getElementById(
                'fare-section'
            );

        const farePerPassenger =
            document.getElementById(
                'fare-per-passenger'
            );

        const totalFare =
            document.getElementById(
                'total-fare'
            );


        if (
            !scheduleField ||
            !sourceField ||
            !destinationField ||
            !passengerCountField ||
            !fareSection ||
            !farePerPassenger ||
            !totalFare
        ) {
            return;
        }


        let currentFare = 0;

        let routeStops = [];


        // =====================================================
        // UPDATE TOTAL FARE
        // =====================================================

        function updateTotalFare() {

            const passengerCount =
                parseInt(
                    passengerCountField.value
                ) || 1;


            const total =
                currentFare *
                passengerCount;


            farePerPassenger.textContent =
                currentFare.toFixed(2);

            totalFare.textContent =
                total.toFixed(2);

        }


        // =====================================================
        // UPDATE DESTINATION OPTIONS
        // =====================================================

        function updateDestinationOptions() {

            const sourceId =
                sourceField.value;


            destinationField.innerHTML = '';


            destinationField.appendChild(
                new Option(
                    'Select destination',
                    ''
                )
            );


            if (!sourceId) {
                return;
            }


            const sourceStop =
                routeStops.find(
                    function (stop) {

                        return String(
                            stop.id
                        ) === String(
                            sourceId
                        );

                    }
                );


            if (!sourceStop) {
                return;
            }


            const sourceOrder =
                Number(
                    sourceStop.order
                );


            routeStops.forEach(
                function (stop) {

                    const stopOrder =
                        Number(
                            stop.order
                        );


                    if (
                        stopOrder >
                        sourceOrder
                    ) {

                        destinationField.appendChild(
                            new Option(
                                `${stop.order}. ${stop.name}`,
                                stop.id
                            )
                        );

                    }

                }
            );


            // Make sure no previous destination remains selected.
            destinationField.value = '';

        }


        // =====================================================
        // CALCULATE FARE
        // =====================================================

        function calculateFare() {

            const sourceId =
                sourceField.value;

            const destinationId =
                destinationField.value;


            // -------------------------------------------------
            // Source or destination not selected
            // -------------------------------------------------

            if (
                !sourceId ||
                !destinationId
            ) {

                currentFare = 0;

                fareSection.style.display =
                    'none';

                updateTotalFare();

                return;
            }


            // -------------------------------------------------
            // Find selected stops
            // -------------------------------------------------

            const sourceStop =
                routeStops.find(
                    function (stop) {

                        return String(
                            stop.id
                        ) === String(
                            sourceId
                        );

                    }
                );


            const destinationStop =
                routeStops.find(
                    function (stop) {

                        return String(
                            stop.id
                        ) === String(
                            destinationId
                        );

                    }
                );


            if (
                !sourceStop ||
                !destinationStop
            ) {

                currentFare = 0;

                fareSection.style.display =
                    'none';

                updateTotalFare();

                return;
            }


            // -------------------------------------------------
            // Destination must come after source
            // -------------------------------------------------

            if (
                sourceStop.order >=
                destinationStop.order
            ) {

                currentFare = 0;

                fareSection.style.display =
                    'block';


                farePerPassenger.textContent =
                    '0.00';

                totalFare.textContent =
                    '0.00';


                console.log(
                    'Invalid journey: destination must come after source.'
                );

                return;
            }


            // -------------------------------------------------
            // Calculate journey distance
            // -------------------------------------------------

            const distance =
                destinationStop
                    .distance_from_start_km
                -
                sourceStop
                    .distance_from_start_km;


            console.log(
                'Journey distance:',
                distance,
                'km'
            );


            if (distance <= 0) {

                currentFare = 0;

                fareSection.style.display =
                    'none';

                updateTotalFare();

                return;
            }


            // -------------------------------------------------
            // Ask server to calculate fare
            // -------------------------------------------------

            currentFare = 0;

            farePerPassenger.textContent =
                'Calculating...';

            totalFare.textContent =
                'Calculating...';

            fareSection.style.display =
                'block';


            fetch(
                `${bookingFareUrl}?schedule_id=${scheduleField.value}&source_stop_id=${sourceId}&destination_stop_id=${destinationId}`,
                {
                    headers: {
                        'X-Requested-With':
                            'XMLHttpRequest'
                    }
                }
            )
            .then(function (response) {

                if (!response.ok) {

                    throw new Error(
                        'Failed to calculate fare.'
                    );

                }

                return response.json();

            })
            .then(function (data) {

                if (!data.success) {

                    currentFare = 0;

                    fareSection.style.display =
                        'block';

                    farePerPassenger.textContent =
                        '0.00';

                    totalFare.textContent =
                        '0.00';


                    console.error(
                        'Fare calculation failed:',
                        data.message
                    );

                    return;
                }


                currentFare =
                    parseFloat(
                        data.fare
                    ) || 0;


                console.log(
                    'Calculated fare per passenger:',
                    currentFare
                );


                fareSection.style.display =
                    'block';


                updateTotalFare();

            })
            .catch(function (error) {

                console.error(
                    'Error calculating fare:',
                    error
                );


                currentFare = 0;


                fareSection.style.display =
                    'none';


                updateTotalFare();

            });

        }


        // =====================================================
        // LOAD ROUTE STOPS
        // =====================================================

        function loadStops(scheduleId) {

            sourceField.innerHTML = '';

            destinationField.innerHTML = '';


            sourceField.appendChild(
                new Option(
                    'Select source',
                    ''
                )
            );


            destinationField.appendChild(
                new Option(
                    'Select destination',
                    ''
                )
            );


            fareSection.style.display =
                'none';


            currentFare = 0;

            routeStops = [];


            updateTotalFare();


            if (!scheduleId) {
                return;
            }


            fetch(
                `${bookingStopsUrl}?schedule_id=${scheduleId}`,
                {
                    headers: {
                        'X-Requested-With':
                            'XMLHttpRequest'
                    }
                }
            )
            .then(function (response) {

                if (!response.ok) {

                    throw new Error(
                        'Failed to load stops.'
                    );

                }

                return response.json();

            })
            .then(function (data) {

                if (!data.success) {

                    console.error(
                        'Unable to load stops:',
                        data.message
                    );

                    return;
                }


                routeStops =
                    data.stops;


                console.log(
                    'Route stops loaded:',
                    routeStops
                );


                data.stops.forEach(
                    function (stop) {

                        sourceField.appendChild(
                            new Option(
                                `${stop.order}. ${stop.name}`,
                                stop.id
                            )
                        );

                    }
                );

            })
            .catch(function (error) {

                console.error(
                    'Error loading stops:',
                    error
                );

            });

        }


        // =====================================================
        // SCHEDULE CHANGE
        // =====================================================

        scheduleField.addEventListener(
            'change',
            function () {

                loadStops(
                    this.value
                );

            }
        );


        // =====================================================
        // SOURCE CHANGE
        // =====================================================

        sourceField.addEventListener(
            'change',
            function () {

                updateDestinationOptions();

                calculateFare();

            }
        );


        // =====================================================
        // DESTINATION CHANGE
        // =====================================================

        destinationField.addEventListener(
            'change',
            function () {

                calculateFare();

            }
        );


        // =====================================================
        // PASSENGER COUNT CHANGE
        // =====================================================

        passengerCountField.addEventListener(
            'input',
            updateTotalFare
        );

    }
);