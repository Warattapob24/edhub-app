document.addEventListener('DOMContentLoaded', () => {
    const importModalElement = document.getElementById('importPlanModal');
    const viewLogsModalElement = document.getElementById('viewLogsModal');
    if (!importModalElement || !viewLogsModalElement) return;

    const importModal = new bootstrap.Modal(importModalElement);
    const viewLogsModal = new bootstrap.Modal(viewLogsModalElement);

    // Import Modal Elements
    const subjectNameEl = document.getElementById('importSubjectName');
    const targetYearNameEl = document.getElementById('importTargetYearName');
    const targetSemesterTermEl = document.getElementById('importTargetSemesterTerm');
    const subjectIdInput = document.getElementById('importSubjectId');
    const targetYearIdInput = document.getElementById('importTargetYearId');
    const previousPlansList = document.getElementById('previousPlansList');
    const confirmImportBtn = document.getElementById('confirmImportBtn');
    const createBlankBtn = document.getElementById('confirmCreateBlankBtn');
    const importStatusEl = document.getElementById('import-status');

    // View Logs Modal Elements
    const logsContentEl = document.getElementById('previousLogsContent');
    const logsModalLabel = document.getElementById('viewLogsModalLabel');

    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    let selectedSourcePlanId = null;

    // --- Function to fetch and display previous plans ---
    async function loadPreviousPlans(subjectId, targetYearId) {
        previousPlansList.innerHTML = `<div class="list-group-item text-center"><div class="spinner-border spinner-border-sm"></div> กำลังค้นหา...</div>`;
        confirmImportBtn.disabled = true;
        selectedSourcePlanId = null; // Reset selection

        try {
            const response = await fetch(`/teacher/api/subject/${subjectId}/previous-plans?target_year_id=${targetYearId}`);
            if (!response.ok) throw new Error('ไม่สามารถค้นหาแผนเดิมได้');
            const plans = await response.json();

            if (plans.length === 0) {
                previousPlansList.innerHTML = `<div class="list-group-item text-muted">ไม่พบแผนการสอนเดิมสำหรับวิชานี้</div>`;
                return;
            }

            previousPlansList.innerHTML = ''; // Clear loading
            plans.forEach(plan => {
                const item = document.createElement('a');
                item.href = '#';
                item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
                item.dataset.planId = plan.plan_id;

                item.innerHTML = `
                    <div>
                        <i class="bi bi-journal-text me-2"></i>
                        ปีการศึกษา ${plan.year} (สร้างโดย: ${plan.teacher_names || 'ไม่ระบุ'})
                    </div>
                    ${plan.has_logs ? `
                        <button type="button" class="btn btn-sm btn-outline-info view-logs-btn" data-plan-id="${plan.plan_id}" data-plan-year="${plan.year}">
                            <i class="bi bi-eye-fill"></i> ดูบันทึกหลังสอน
                        </button>
                    ` : '<span class="text-muted small">ไม่มีบันทึก</span>'}
                `;
                previousPlansList.appendChild(item);
            });

        } catch (error) {
            console.error("Error loading previous plans:", error);
            previousPlansList.innerHTML = `<div class="list-group-item text-danger">${error.message}</div>`;
        }
    }

    // --- Event listener when Import Modal is shown ---
    importModalElement.addEventListener('show.bs.modal', (event) => {
        const button = event.relatedTarget;
        const subjectId = button.dataset.subjectId;
        const targetYearId = button.dataset.targetYearId;

        subjectNameEl.textContent = button.dataset.subjectName;
        targetYearNameEl.textContent = button.dataset.targetYearName;
        targetSemesterTermEl.textContent = button.dataset.targetSemesterTerm;
        subjectIdInput.value = subjectId;
        targetYearIdInput.value = targetYearId;
        importStatusEl.textContent = ''; // Clear status

        // Reset button states
        confirmImportBtn.disabled = true;
        createBlankBtn.disabled = false;
        confirmImportBtn.querySelector('.spinner-border').classList.add('d-none');
        createBlankBtn.querySelector('.spinner-border').classList.add('d-none');

        loadPreviousPlans(subjectId, targetYearId);
    });

    // --- Event listener for selecting a previous plan ---
    previousPlansList.addEventListener('click', (event) => {
        const target = event.target;
        const planItem = target.closest('a.list-group-item[data-plan-id]');
        const viewLogsBtn = target.closest('.view-logs-btn');

        if (viewLogsBtn && planItem) {
            event.preventDefault(); // Prevent selection when clicking "View Logs"
            event.stopPropagation(); // Stop event bubbling up to the planItem click listener
            const planId = viewLogsBtn.dataset.planId;
            const planYear = viewLogsBtn.dataset.planYear;
            logsModalLabel.textContent = `บันทึกหลังสอน (ปีการศึกษา ${planYear})`;
            logsContentEl.innerHTML = `<div class="text-center"><div class="spinner-border"></div></div>`;
            viewLogsModal.show();

            fetch(`/teacher/api/plan/${planId}/teaching-logs`)
                .then(response => {
                    if (!response.ok) throw new Error('Failed to load logs');
                    return response.text(); // Expecting HTML partial
                })
                .then(html => {
                    logsContentEl.innerHTML = html;
                })
                .catch(error => {
                    logsContentEl.innerHTML = `<div class="alert alert-danger">${error.message}</div>`;
                });

        } else if (planItem) {
            event.preventDefault();
            // Toggle selection UI
            previousPlansList.querySelectorAll('a').forEach(a => a.classList.remove('active'));
            planItem.classList.add('active');
            selectedSourcePlanId = planItem.dataset.planId;
            confirmImportBtn.disabled = false; // Enable import button
        }
    });

    // --- Function to handle the final import/create action ---
    async function handleImportOrCreate(sourcePlanId = null) {
        const subjectId = subjectIdInput.value;
        const targetYearId = targetYearIdInput.value;
        const isImporting = sourcePlanId !== null;

        const buttonToSpin = isImporting ? confirmImportBtn : createBlankBtn;
        const otherButton = isImporting ? createBlankBtn : confirmImportBtn;

        buttonToSpin.disabled = true;
        otherButton.disabled = true;
        buttonToSpin.querySelector('.spinner-border').classList.remove('d-none');
        importStatusEl.textContent = isImporting ? 'กำลังนำเข้าแผน...' : 'กำลังสร้างแผนใหม่...';
        importStatusEl.classList.remove('text-danger', 'text-success');

        try {
            const response = await fetch('/teacher/api/lesson-plan/import', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    subject_id: parseInt(subjectId),
                    target_academic_year_id: parseInt(targetYearId),
                    source_plan_id: sourcePlanId ? parseInt(sourcePlanId) : null
                })
            });

            const result = await response.json();

            if (response.ok && result.status === 'success' && result.new_plan_id) {
                importStatusEl.textContent = 'สำเร็จ!';
                importStatusEl.classList.add('text-success');
                importModal.hide();
                Swal.fire({
                    icon: 'success',
                    title: isImporting ? 'นำเข้าสำเร็จ!' : 'สร้างแผนใหม่สำเร็จ!',
                    text: 'ระบบได้สร้างแผนการสอนในสถานะฉบับร่างเรียบร้อยแล้ว',
                    timer: 2000,
                    showConfirmButton: false
                }).then(() => {
                    window.location.href = `/teacher/plan/${result.new_plan_id}/workspace`;
                });
            } else {
                throw new Error(result.message || 'เกิดข้อผิดพลาดไม่ทราบสาเหตุ');
            }

        } catch (error) {
            console.error("Import/Create error:", error);
            importStatusEl.textContent = `ผิดพลาด: ${error.message}`;
            importStatusEl.classList.add('text-danger');
            buttonToSpin.disabled = false;
            // Re-enable create blank button always, re-enable import only if a plan was selected
            otherButton.disabled = isImporting ? false : (selectedSourcePlanId === null);
            buttonToSpin.querySelector('.spinner-border').classList.add('d-none');
        }
    }

    // --- Event listeners for the action buttons ---
    confirmImportBtn.addEventListener('click', () => {
        if (selectedSourcePlanId) {
            handleImportOrCreate(selectedSourcePlanId);
        }
    });

    createBlankBtn.addEventListener('click', () => {
        handleImportOrCreate(null); // Pass null for source_plan_id
    });
});