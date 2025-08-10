$(document).ready(function() {
    // Initialize DataTable
    $('#employees-table').DataTable({
        responsive: true
    });

    // Save employee
    $('#saveEmployee').click(function() {
        const formData = new FormData();
        formData.append('name', $('#name').val());
        formData.append('department', $('#department').val());
        formData.append('position', $('#position').val());
        formData.append('photo', $('#photo')[0].files[0]);

        $.ajax({
            url: '/add_employee',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function(response) {
                location.reload();
            },
            error: function(xhr) {
                alert('Error: ' + xhr.responseJSON.error);
            }
        });
    });

    // Edit employee (placeholder)
    $(document).on('click', '.edit-btn', function() {
        const employeeId = $(this).data('id');
        alert('Edit employee with ID: ' + employeeId);
    });

    // Delete employee (placeholder)
    $(document).on('click', '.delete-btn', function() {
        const employeeId = $(this).data('id');
        if (confirm('Are you sure you want to delete this employee?')) {
            $.ajax({
                url: '/delete_employee/' + employeeId,
                type: 'DELETE',
                success: function(response) {
                    location.reload();
                },
                error: function(xhr) {
                    alert('Error: ' + xhr.responseJSON.error);
                }
            });
        }
    });
});