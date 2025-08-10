$(document).ready(function() {
    // Initialize DataTable
    const attendanceTable = $('#attendance-table').DataTable({
        ajax: {
            url: '/attendance_data',
            dataSrc: ''
        },
        columns: [
            { data: 'id' },
            { data: 'name' },
            { data: 'department' },
            { data: 'timestamp' }
        ],
        order: [[3, 'desc']],
        responsive: true
    });

    // Set default date to today
    const today = new Date().toISOString().split('T')[0];
    $('#attendance-date').val(today);

    // Update stats
    function updateStats() {
        $.get('/stats', function(data) {
            $('#total-employees').text(data.total_employees);
            $('#today-attendance').text(data.today_attendance);
            $('#camera-status').html(
                `<i class="bi bi-camera-video${data.status === 'Active' ? '-fill text-success' : '-off text-danger'}"></i> ` +
                `Camera is currently ${data.status.toLowerCase()}`
            );
        });
    }

    // Update recent attendance
    function updateRecentAttendance() {
        $.get('/attendance_data', {date: today}, function(data) {
            const recent = data.slice(0, 5);
            $('#recent-attendance').empty();
            recent.forEach(item => {
                $('#recent-attendance').append(`
                    <tr>
                        <td>${item.name}</td>
                        <td>${item.timestamp.split(' ')[1]}</td>
                    </tr>
                `);
            });
        });
    }

    // Camera control
    $('#start-camera').click(function() {
        $.post('/start_camera', function() {
            $('#start-camera').prop('disabled', true);
            $('#stop-camera').prop('disabled', false);
            updateCameraFeed();
        });
    });

    $('#stop-camera').click(function() {
        $.post('/stop_camera', function() {
            $('#start-camera').prop('disabled', false);
            $('#stop-camera').prop('disabled', true);
            $('#live-frame').attr('src', '');
        });
    });

    // Update camera feed
    function updateCameraFeed() {
        $.get('/get_frame', function(data) {
            if (data.frame) {
                $('#live-frame').attr('src', 'data:image/jpeg;base64,' + data.frame);
            }
            if ($('#stop-camera').is(':disabled') === false) {
                setTimeout(updateCameraFeed, 100);
            }
        });
    }

    // Download attendance
    $('#download-attendance').click(function() {
        const date = $('#attendance-date').val();
        window.location.href = `/download_attendance?date=${date}`;
    });

    // Filter attendance by date
    $('#attendance-date').change(function() {
        const date = $(this).val();
        attendanceTable.ajax.url(`/attendance_data?date=${date}`).load();
    });

    // Initial updates
    updateStats();
    updateRecentAttendance();

    // Update stats every 30 seconds
    setInterval(function() {
        updateStats();
        updateRecentAttendance();
    }, 30000);
});