
// Dashboard JavaScript - Professional Analytics

document.addEventListener('DOMContentLoaded', function () {
    initializeCharts();
    setupSearch();
    setupExport();
});

// Initialize Chart.js charts
function initializeCharts() {
    // Processing Time Trend Chart
    const processingCtx = document.getElementById('processingChart');
    if (processingCtx) {
        new Chart(processingCtx, {
            type: 'line',
            data: {
                labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                datasets: [{
                    label: 'Processing Time (seconds)',
                    data: [2.3, 2.1, 2.5, 2.2, 2.0, 2.4, 2.1],
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointBackgroundColor: '#8b5cf6',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: '#1a1a1a',
                        titleColor: '#fff',
                        bodyColor: '#a0a0a0',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false,
                        callbacks: {
                            label: function (context) {
                                return context.parsed.y.toFixed(2) + 's';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)',
                            borderColor: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#a0a0a0',
                            callback: function (value) {
                                return value + 's';
                            }
                        }
                    },
                    x: {
                        grid: {
                            display: false,
                            borderColor: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#a0a0a0'
                        }
                    }
                }
            }
        });
    }

    // Quality Distribution Chart
    const qualityCtx = document.getElementById('qualityChart');
    if (qualityCtx) {
        new Chart(qualityCtx, {
            type: 'doughnut',
            data: {
                labels: ['Excellent (90-100)', 'Good (80-89)', 'Fair (70-79)', 'Poor (<70)'],
                datasets: [{
                    data: [45, 30, 20, 5],
                    backgroundColor: [
                        '#10b981',
                        '#3b82f6',
                        '#f59e0b',
                        '#ef4444'
                    ],
                    borderColor: '#0a0a0a',
                    borderWidth: 3,
                    hoverOffset: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#a0a0a0',
                            padding: 15,
                            font: {
                                size: 11
                            },
                            usePointStyle: true,
                            pointStyle: 'circle'
                        }
                    },
                    tooltip: {
                        backgroundColor: '#1a1a1a',
                        titleColor: '#fff',
                        bodyColor: '#a0a0a0',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        padding: 12,
                        callbacks: {
                            label: function (context) {
                                const label = context.label || '';
                                const value = context.parsed || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((value / total) * 100).toFixed(1);
                                return label + ': ' + value + ' (' + percentage + '%)';
                            }
                        }
                    }
                },
                cutout: '65%'
            }
        });
    }
}

// Search functionality
function setupSearch() {
    const searchInput = document.getElementById('searchInput');
    if (!searchInput) return;

    searchInput.addEventListener('input', function (e) {
        const searchTerm = e.target.value.toLowerCase();
        const rows = document.querySelectorAll('.table-row');

        rows.forEach(row => {
            const filename = row.querySelector('.filename-cell span').textContent.toLowerCase();
            const date = row.querySelector('.date-cell .date').textContent.toLowerCase();

            if (filename.includes(searchTerm) || date.includes(searchTerm)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });

        // Update record count
        const visibleRows = Array.from(rows).filter(row => row.style.display !== 'none').length;
        const recordCount = document.querySelector('.record-count');
        if (recordCount) {
            const totalRows = rows.length;
            if (searchTerm) {
                recordCount.textContent = `${visibleRows} of ${totalRows} records`;
            } else {
                recordCount.textContent = `${totalRows} records`;
            }
        }
    });
}

// Export functionality
function setupExport() {
    const exportBtn = document.querySelector('.btn-export');
    if (!exportBtn) return;

    exportBtn.addEventListener('click', function () {
        // Get table data
        const table = document.querySelector('.data-table');
        if (!table) return;

        const rows = Array.from(table.querySelectorAll('tbody tr'));
        const headers = Array.from(table.querySelectorAll('thead th'))
            .map(th => th.textContent.trim());

        // Prepare CSV data
        let csvContent = headers.join(',') + '\n';

        rows.forEach(row => {
            if (row.style.display === 'none') return; // Skip hidden rows

            const cells = Array.from(row.querySelectorAll('td'));
            const rowData = [];

            // Extract text content from each cell
            cells.forEach((cell, index) => {
                let text = '';

                if (index === 0) { // Date column
                    const date = cell.querySelector('.date')?.textContent || '';
                    const time = cell.querySelector('.time')?.textContent || '';
                    text = `${date} ${time}`;
                } else if (index === 1) { // Filename column
                    text = cell.querySelector('.filename-cell span')?.textContent || '';
                } else if (index === 4) { // Quality column
                    text = cell.querySelector('.quality-badge')?.textContent ||
                        cell.querySelector('.text-muted')?.textContent || '';
                } else if (index === 5) { // Status column
                    text = cell.querySelector('.status-badge')?.textContent || '';
                } else if (index === 6) { // Actions column
                    text = 'View/Download';
                } else {
                    text = cell.textContent.trim();
                }

                // Escape commas and quotes in CSV
                text = text.replace(/"/g, '""');
                if (text.includes(',') || text.includes('"') || text.includes('\n')) {
                    text = `"${text}"`;
                }

                rowData.push(text);
            });

            csvContent += rowData.join(',') + '\n';
        });

        // Create download link
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', `colorization_history_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';

        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        // Show feedback
        const originalText = exportBtn.innerHTML;
        exportBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12"/>
            </svg>
            Exported!
        `;
        exportBtn.style.background = 'rgba(16, 185, 129, 0.15)';
        exportBtn.style.color = '#10b981';
        exportBtn.style.borderColor = '#10b981';

        setTimeout(() => {
            exportBtn.innerHTML = originalText;
            exportBtn.style.background = '';
            exportBtn.style.color = '';
            exportBtn.style.borderColor = '';
        }, 2000);
    });
}

// Time range selector handler (for future implementation)
document.querySelectorAll('.time-range-select').forEach(select => {
    select.addEventListener('change', function () {
        // TODO: Fetch new data based on selected time range
        console.log('Time range changed to:', this.value);
    });
});
