
document.addEventListener('DOMContentLoaded', function () {
    // --- CORE STATE & CONSTANTS ---
    const unitList = document.getElementById('unitList');
    const workspaceTabs = document.getElementById('workspaceTabs');
    const workspaceTabsContent = document.getElementById('workspaceTabsContent');
    const planId = unitList.dataset.planId; 
    const addIndicatorUrl = unitList.dataset.addIndicatorUrl;    
    const csrfToken = '{{ form.csrf_token._value() }}';
    const subUnitEditModal = new bootstrap.Modal(document.getElementById('subUnitEditModal'));
    let activeUnitId = null;
    let subUnitIndicatorsTomSelect = null;
    let subUnitGradedItemsTomSelect = null;
    let tomSelect = null;
    let hourSaveDebounce;
    let debounceTimeout;
    let targetMidRatio = 80;
    let targetFinalRatio = 20;
    let isTargetSetByUser = false;
    let unitHoursData = {};

    document.querySelectorAll('#unitList a').forEach(link => {
        unitHoursData[link.dataset.unitId] = 0;
    });
    // --- MODAL INSTANCES ---
    const unitFormModal = new bootstrap.Modal(document.getElementById('unitFormModal'));
    const selectionModal = new bootstrap.Modal(document.getElementById('selectTopicsModal'));

    // --- CENTRALIZED EVENT LISTENERS ---

    // 1. Unit List Management (Select, Delete)
    unitList.addEventListener('click', (e) => {
        const unitLink = e.target.closest('a.list-group-item');
        const deleteBtn = e.target.closest('.delete-unit-btn');

        if (deleteBtn) {
            e.preventDefault();
            e.stopPropagation();
        } else if (unitLink) {
            e.preventDefault();
            const clickedUnitId = unitLink.dataset.unitId;

            // Check if the Gradebook tab is the active one
            const gradebookTab = document.getElementById('gradebook-tab');
            if (gradebookTab && gradebookTab.classList.contains('active')) {
                // If yes, just filter the columns without reloading everything
                setActiveUnitFilter(clickedUnitId);
                filterGradebookColumns(clickedUnitId);
            } else {
                // If another tab is active, use the original behavior
                if (clickedUnitId !== activeUnitId) {
                    setActiveUnit(clickedUnitId);
                }
            }
            updateManageGroupsButtonState();
        }
    });

    // 2. Tab Switching (FINAL, CORRECTED ARCHITECTURE)
    workspaceTabs.addEventListener('show.bs.tab', (event) => {
        const clickedTabButton = event.target;
        const tabId = clickedTabButton.id;
        const paneId = clickedTabButton.dataset.bsTarget.substring(1);

        // Logic การตัดสินใจ:
        // ถ้าเป็นแท็บ Gradebook ให้เรียกฟังก์ชันของมันโดยตรง
        if (tabId === 'gradebook-tab') {
            loadTabContent(null, paneId); // ส่ง unitId เป็น null
            return; // จบการทำงานในส่วนนี้
        }
        // ถ้าเป็นแท็บอื่นๆ ให้ตรวจสอบว่าเลือก unit แล้วหรือยัง
        if (activeUnitId) {
            // กรณีปกติ: มี unit ถูกเลือกไว้อยู่แล้ว
            loadTabContent(activeUnitId, paneId);
        } else {
            // กรณีพิเศษ: ยังไม่มี unit ไหนถูกเลือก
            const firstUnitLink = unitList.querySelector('a.list-group-item');
            if (firstUnitLink) {
                // ถ้าเจอ unit แรกในรายการ
                const firstUnitId = firstUnitLink.dataset.unitId;

                // 1. กำหนด unit แรกให้เป็น activeUnitId ทันที
                activeUnitId = firstUnitId;

                // 2. อัปเดต UI ของแถบเมนูด้านซ้ายให้แสดงว่า unit แรกถูกเลือกแล้ว
                document.querySelectorAll('#unitList a').forEach(a => {
                    a.classList.toggle('active', a.dataset.unitId === firstUnitId);
                });
                document.getElementById('initial-message')?.remove();

                // 3. สั่งโหลดเนื้อหาของ "แท็บที่ผู้ใช้กด" โดยใช้ "unit แรก"
                loadTabContent(firstUnitId, paneId);

            } else {
                // กรณีที่ไม่มี unit ในรายการเลย
                event.preventDefault(); // หยุดการสลับแท็บ
                Swal.fire('ไม่พบหน่วยการเรียนรู้', 'กรุณาสร้างหน่วยการเรียนรู้ก่อน', 'warning');
            }
        }
    });

    // เพิ่ม Event Listener นี้เข้าไป
    document.addEventListener('shown.bs.tab', function(event) {
        // ตรวจสอบว่าแท็บที่เพิ่งแสดงคือแท็บ "ตั้งค่าการประเมิน" หรือไม่
        if (event.target.getAttribute('href') === '#assessment-content') {
            console.log('Assessment tab shown, calling update functions.');
            // เมื่อ DOM พร้อมแล้ว จึงค่อยเรียกฟังก์ชันคำนวณ
            loadRatioTarget().then(updateSummaryPanel);
        }
    });

    // 3. Dynamic Content Interactions (via Event Delegation)
    workspaceTabsContent.addEventListener('click', (e) => {
        // Assessment Tab Buttons
        const deleteItemBtn = e.target.closest('.delete-graded-item-btn');
        const selectTopicsBtn = e.target.closest('.select-topics-btn');

        if (deleteItemBtn) {
            handleGradedItemDelete(deleteItemBtn.dataset.itemId);
        }
        if (selectTopicsBtn) {
            openTopicSelectionModal(selectTopicsBtn);
        }

        // Lesson Plan Tab Buttons
        const addSubUnitBtn = e.target.closest('#add-subunit-btn');
        const editSubUnitBtn = e.target.closest('.edit-subunit-btn');
        const deleteSubUnitBtn = e.target.closest('.delete-subunit-btn');

        if (addSubUnitBtn) {
            handleAddSubUnit(addSubUnitBtn);
        }
        if (editSubUnitBtn) {
            handleEditSubUnit(editSubUnitBtn);
        }
        if (deleteSubUnitBtn) {
            handleDeleteSubUnit(deleteSubUnitBtn);
        }
    });

    // 4. Unit Creation Form
    document.getElementById('unit-form').addEventListener('submit', handleUnitCreate);
    document.getElementById('unitFormModal').addEventListener('show.bs.modal', (event) => {
        const button = event.relatedTarget;
        if (button && button.dataset.bsAction === 'add') {
            const modal = event.currentTarget;
            modal.querySelector('.modal-title').textContent = 'สร้างหน่วยการเรียนรู้ใหม่';
            modal.querySelector('form').reset();
            modal.querySelector('#modal-unit-id').value = '';
        }
    });

    workspaceTabsContent.addEventListener('change', e => {
        if (e.target.matches('.exam-score-switch, .exam-score-input')) {
            handleExamScoreChange(e);
        }
    });
    
    // --- CORE FUNCTIONS ---

    /**
     * Sets the active unit, updates UI, and loads content for the current tab.
     * This is the central function for changing context.
     * @param {string} unitId The ID of the unit to activate.
     */
    function setActiveUnit(unitId) {
        if (!unitId) return;
        activeUnitId = unitId;

        // Update left sidebar visual state
        document.querySelectorAll('#unitList a').forEach(a => {
            a.classList.toggle('active', a.dataset.unitId === unitId);
        });

        // Ensure the initial 'please select' placeholder is removed
        document.getElementById('initial-message')?.remove();

        // Determine which tab is currently active and make sure its pane is visible
        const activeTabButton = workspaceTabs.querySelector('.nav-link.active');
        if (activeTabButton) {
            const paneId = activeTabButton.dataset.bsTarget.substring(1);
            // Deactivate other panes, activate the target pane so loaded content is visible
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('show', 'active'));
            const targetPane = document.getElementById(paneId);
            if (targetPane) targetPane.classList.add('show', 'active');

            // Load the pane content for the selected unit
            loadTabContent(unitId, paneId);
        }
    }

    /**
     * สร้าง HTML สำหรับแสดงป้ายแจ้งเตือน (Alert Badges)
     * @param {object} alerts - อ็อบเจกต์การแจ้งเตือน เช่น { 'ติด 0': 'คะแนนไม่ถึงครึ่ง' }
     * @returns {string} - โค้ด HTML ของป้ายแจ้งเตือน
     */
    function renderAlerts(alerts) {
        if (!alerts || Object.keys(alerts).length === 0) return '';
        
        let badgesHtml = '';
        for (const key in alerts) {
            const message = alerts[key];
            // --- NEW: Add condition for different badge color ---
            let badgeClass = 'bg-danger'; // Default to red for '0' and 'ร'
            if (key === 'กรอกคะแนน') {
                badgeClass = 'bg-info text-dark'; // Use blue for "Enter Scores"
            }
            badgesHtml += ` <span class="badge ${badgeClass} ms-1" title="${message}">${key}</span>`;
        }
        return badgesHtml;
    }

    // --- FUNCTIONS ---

    // =======================================================
    // NEW GRADEBOOK ARCHITECTURE (FINAL)
    // =======================================================
    // Global variables for grouping
    const groupModal = new bootstrap.Modal(document.getElementById('groupManagementModal'));
    let allEnrollments = []; // Stores {id, name, roll_number}
    let sortableInstances = []; // To keep track of Sortable instances

    /**
     * Entry point when "Manage Groups" button is clicked.
     */
    async function openGroupManager() {
        const classroomSelector = document.getElementById('classroom-selector');
        const courseId = classroomSelector.options[classroomSelector.selectedIndex].dataset.courseId;
        
        const loader = document.getElementById('group-manager-loader');
        const content = document.getElementById('group-manager-content');
        loader.classList.remove('d-none');
        content.style.display = 'none';

        try {
            const groupsUrlTemplate = unitList.dataset.groupsUrl;
            const groupsUrl = `${groupsUrlTemplate}?unit_id=${activeUnitId}`;
                        
            const [enrollmentsResponse, groupsResponse] = await Promise.all([
                fetch(`/teacher/api/classrooms/${classroomSelector.value}/enrollments`),
                fetch(groupsUrl)
            ]);
            if (!enrollmentsResponse.ok || !groupsResponse.ok) throw new Error('ไม่สามารถโหลดข้อมูลได้');

            allEnrollments = await enrollmentsResponse.json();
            const groups = await groupsResponse.json();
            
            renderGroupManagerUI(groups);

            groupModal.show();
            
            content.style.display = 'flex';
        } catch (error) {
            console.error("Failed to open group manager:", error);
            loader.textContent = 'เกิดข้อผิดพลาดในการโหลดข้อมูล';
        } finally {
            // Hide loader in a way that doesn't cause a layout shift if there's an error
            if(loader.classList.contains('d-none') == false) {
            loader.classList.add('d-none');
            }
        }
    }

    /**
     * อัปเดตสถานะ (เปิด/ปิด) ของปุ่ม "จัดการกลุ่ม"
     * ปุ่มจะกดได้ก็ต่อเมื่อมีการเลือกหน่วยการเรียนรู้และห้องเรียนแล้วเท่านั้น
     */
    function updateManageGroupsButtonState() {
        const manageGroupsBtn = document.getElementById('manage-groups-btn');
        const classroomSelector = document.getElementById('classroom-selector');
        if (manageGroupsBtn && classroomSelector) {
            // ปุ่มจะ enable (disabled = false) เมื่อ activeUnitId ไม่ใช่ null และมีการเลือกห้องเรียนแล้ว
            const isEnabled = activeUnitId !== null && classroomSelector.value !== '';
            manageGroupsBtn.disabled = !isEnabled;
        }
    }

    /**
     * Renders the entire UI inside the group management modal.
     */
    function renderGroupManagerUI(groups) {
        const ungroupedList = document.getElementById('ungrouped-students-list');
        const groupsContainer = document.getElementById('groups-container');
        
        ungroupedList.innerHTML = '';
        groupsContainer.innerHTML = '';

        const groupedEnrollmentIds = new Set(groups.flatMap(g => g.enrollments));
        
        allEnrollments.forEach(en => {
            if (!groupedEnrollmentIds.has(en.id)) {
                ungroupedList.innerHTML += createStudentElement(en);
            }
        });

        groups.forEach(group => {
            let membersHtml = '';
            group.enrollments.forEach(enId => {
                const enrollment = allEnrollments.find(e => e.id === enId);
                if(enrollment) membersHtml += createStudentElement(enrollment);
            });
            groupsContainer.innerHTML += createGroupCard(group, membersHtml);
        });

        // เรียกใช้ฟังก์ชันติดตั้ง Sortable ที่เราสร้างขึ้นใหม่
        initializeAllSortables();
    }

    /**
     * Creates a student element for SortableJS.
     */
    function createStudentElement(enrollment) {
        return `<div class="list-group-item list-group-item-action p-2" data-enrollment-id="${enrollment.id}">
                    <small>${enrollment.roll_number}. ${enrollment.name}</small>
                </div>`;
    }

    /**
     * Creates a group card element with a dropzone.
     */
    function createGroupCard(group, membersHtml) {
        return `<div class="card mb-3" data-group-id="${group.id}">
                    <div class="card-header p-2 d-flex justify-content-between align-items-center">
                        <input type="text" class="form-control form-control-sm group-name-input" value="${group.name}">
                        <button class="btn btn-xs btn-outline-danger ms-2 delete-group-btn border-0"><i class="bi bi-trash"></i></button>
                    </div>
                    <div class="card-body p-2 list-group group-dropzone" style="min-height: 50px;">
                        ${membersHtml}
                    </div>
                </div>`;
    }

    /**
     * Initializes or re-initializes SortableJS on all group containers.
     * This is a safe way to activate drag-and-drop.
     */
    function initializeAllSortables() {
        sortableInstances.forEach(s => s.destroy()); // เคลียร์ instance เก่าทิ้งก่อน
        sortableInstances = [];

        const allLists = document.querySelectorAll('#ungrouped-students-list, .group-dropzone');
        allLists.forEach(listEl => {
            const sortable = new Sortable(listEl, {
                group: 'students', // ชื่อกลุ่มต้องตรงกันเพื่อให้ลากข้ามกลุ่มได้
                animation: 150,
                ghostClass: 'bg-primary-soft' // คลาสสำหรับเงาตอนลาก
            });
            sortableInstances.push(sortable);
        });
    }

    /**
     * Auto-generates groups and distributes students.
     */
    async function autoGenerateGroups() {
        const { value: numGroups } = await Swal.fire({
            title: 'สร้างกลุ่มอัตโนมัติ',
            input: 'number',
            inputLabel: 'คุณต้องการสร้างกี่กลุ่ม?',
            inputPlaceholder: 'ใส่จำนวนกลุ่ม',
            showCancelButton: true,
            confirmButtonText: 'สร้างกลุ่ม',
            cancelButtonText: 'ยกเลิก',
            inputValidator: (value) => {
                if (!value || value < 1) {
                    return 'กรุณาใส่จำนวนกลุ่มที่ถูกต้อง!'
                }
            }
        });

        if (numGroups) {
            const groupsContainer = document.getElementById('groups-container');
            const ungroupedStudents = Array.from(document.querySelectorAll('#ungrouped-students-list [data-enrollment-id]'));
            
            // ลบกลุ่มเก่าทิ้งทั้งหมด
            groupsContainer.innerHTML = '';
            
            // Shuffle students for random distribution
            for (let i = ungroupedStudents.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [ungroupedStudents[i], ungroupedStudents[j]] = [ungroupedStudents[j], ungroupedStudents[i]];
            }
            
            // สร้างการ์ดกลุ่มใหม่ตามจำนวนที่ระบุ
            for (let i = 1; i <= numGroups; i++) {
                groupsContainer.insertAdjacentHTML('beforeend', createGroupCard({ id: `new-${Date.now()}-${i}`, name: `กลุ่มที่ ${i}` }, ''));
            }

            // ติดตั้ง Sortable ให้กับการ์ดใหม่ทั้งหมด
            initializeAllSortables();

            // กระจายนักเรียนเข้ากลุ่ม
            const dropzones = document.querySelectorAll('.group-dropzone');
            if (dropzones.length > 0) {
                ungroupedStudents.forEach((studentNode, index) => {
                    const targetGroupIndex = index % numGroups;
                    dropzones[targetGroupIndex].appendChild(studentNode);
                });
            }
        }
    }

    /**
     * Saves the current state of groups to the backend.
     */
    async function saveGroups() {
        if (!activeUnitId) {
            Swal.fire('เกิดข้อผิดพลาด', 'กรุณาเลือกหน่วยการเรียนรู้ที่ต้องการจัดกลุ่มก่อน', 'error');
            return;
        }        
        const classroomSelector = document.getElementById('classroom-selector');
        const courseId = classroomSelector.options[classroomSelector.selectedIndex].dataset.courseId;
        const groupsContainer = document.getElementById('groups-container');
        
        const payload = { 
            groups: [],
            course_id: courseId 
        };
        
        groupsContainer.querySelectorAll('.card').forEach(card => {
            const groupId = card.dataset.groupId;
            const groupName = card.querySelector('.group-name-input').value;
            const memberEnrollmentIds = Array.from(card.querySelectorAll('[data-enrollment-id]')).map(el => parseInt(el.dataset.enrollmentId));
            
            payload.groups.push({
                id: groupId,
                name: groupName,
                members: memberEnrollmentIds
            });
        });

        try {
            const groupsUrl = unitList.dataset.groupsUrl;
            const saveUrl = `${groupsUrl}?unit_id=${activeUnitId}`;
            
            const response = await fetch(saveUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify(payload)
            });
            if (!response.ok) throw new Error('Server returned an error.');

            const result = await response.json();
            if (result.status === 'success') {
                Swal.fire({ icon: 'success', title: 'บันทึกสำเร็จ!', timer: 1500, showConfirmButton: false });
                groupModal.hide();
                // Reload gradebook to reflect group changes
                fetchAndRenderGradebookTable(classroomSelector, activeUnitId);

            } else {
                Swal.fire('เกิดข้อผิดพลาด', result.message, 'error');
            }
        } catch (error) {
            Swal.fire('เกิดข้อผิดพลาด', 'ไม่สามารถเชื่อมต่อกับ Server ได้', 'error');
        }
    }

    // Event Listeners for the modal
    // Consolidated Event Listeners for the modal using Event Delegation
    document.addEventListener('click', function(e) {
        // --- For the main "Manage Groups" button ---
        if (e.target.matches('#manage-groups-btn') || e.target.closest('#manage-groups-btn')) {
            e.preventDefault();
            openGroupManager();
            return; // End execution here
        }

        // --- For buttons INSIDE the modal ---
        const addNewGroupBtn = e.target.closest('#add-new-group-btn');
        const autoGenerateBtn = e.target.closest('#auto-generate-groups-btn');
        const deleteGroupBtn = e.target.closest('.delete-group-btn');
        const saveGroupsBtn = e.target.closest('#save-groups-btn');

        if (addNewGroupBtn) {
            const groupsContainer = document.getElementById('groups-container');
            const newGroupName = `กลุ่มที่ ${groupsContainer.querySelectorAll('.card').length + 1}`;
            groupsContainer.insertAdjacentHTML('beforeend', createGroupCard({ id: `new-${Date.now()}`, name: newGroupName }, ''));
            initializeAllSortables(); // Re-initialize drag and drop
        } 
        else if (autoGenerateBtn) {
            autoGenerateGroups();
        } 
        else if (deleteGroupBtn) {
            const card = deleteGroupBtn.closest('.card');
            const members = card.querySelectorAll('[data-enrollment-id]');
            document.getElementById('ungrouped-students-list').append(...members);
            card.remove();
        } 
        else if (saveGroupsBtn) {
            saveGroups();
        }
    });

    /**
     * ฟังก์ชันนี้จะถูกเรียกใช้หลังจาก HTML ของแท็บ Gradebook โหลดเสร็จแล้ว
     * หน้าที่: ค้นหาส่วนประกอบและติดตั้งระบบควบคุม (Event Listeners)
     */
    function initializeGradebookTab() {
        const classroomSelector = document.getElementById('classroom-selector');
        const manageGroupsBtn = document.getElementById('manage-groups-btn');

        /**
         * Helper function to enable/disable the "Manage Groups" button
         * based on whether a classroom is selected.
         */
        const updateGroupButtonState = () => {
            // If classroomSelector.value is not empty (i.e., a class is selected),
            // set disabled to false. Otherwise, set it to true.
            manageGroupsBtn.disabled = !classroomSelector.value;
        };

        if (classroomSelector && manageGroupsBtn) {
            const updateButtonState = () => {
                manageGroupsBtn.disabled = !classroomSelector.value;
            };            
            classroomSelector.addEventListener('change', () => {
                updateButtonState();
                let unitToKeepSelected = activeUnitId; // ใช้สถานะหลัก (activeUnitId) เป็นค่าเริ่มต้น
                if (!unitToKeepSelected) {
                    // กรณีที่ยังไม่มีการเลือกหน่วยใดๆ เลย (โหลดหน้าครั้งแรก) ให้เลือกหน่วยแรกสุดในรายการ
                    const firstUnitLink = unitList.querySelector('a.list-group-item');
                    unitToKeepSelected = firstUnitLink ? firstUnitLink.dataset.unitId : null;
                };
                fetchAndRenderGradebookTable(classroomSelector, unitToKeepSelected);
            });

            // --- นี่คือ Logic ใหม่ ---
            // ตรวจสอบว่ามีห้องเรียนให้เลือกหรือไม่ (ตัวเลือกที่ 2 คือห้องแรกจริงๆ)
            if (classroomSelector.options[1]) {
                // สั่งให้เลือกห้องเรียนแรก
                classroomSelector.value = classroomSelector.options[1].value;
                // สั่งให้โปรแกรมทำงานเหมือนกับว่าผู้ใช้เป็นคนเลือกเอง (เพื่อโหลดตาราง)
                classroomSelector.dispatchEvent(new Event('change'));
            }
            updateButtonState();
            updateGroupButtonState();
            updateManageGroupsButtonState();
        }
    }

    /**
     * หน้าที่: ดึงข้อมูลคะแนนดิบจาก API และส่งไปวาดตาราง
     * @param {HTMLSelectElement} selector - Element ของ Dropdown ที่ถูกเลือก
     */
    async function fetchAndRenderGradebookTable(selector, unitIdToSelectAfterRender) {
        const classroomId = selector.value;
        const selectedOption = selector.options[selector.selectedIndex];
        const container = document.getElementById('gradebook-container');

        if (!classroomId) return;
        
        const courseId = selectedOption.dataset.courseId;
        if (!courseId) {
            container.innerHTML = `<div class="alert alert-danger">Error: ไม่พบ Course ID</div>`;
            return;
        }

        try {
            container.innerHTML = '<div class="d-flex justify-content-center p-5"><div class="spinner-border" role="status"></div></div>';
            const response = await fetch(`/teacher/api/course/${courseId}/gradebook-data?classroom_id=${classroomId}`);
            if (!response.ok) throw new Error('ไม่สามารถโหลดข้อมูลคะแนนได้');
            
            const data = await response.json();
            data.course_id = courseId;
        renderGradebookTable(data, container, unitIdToSelectAfterRender);
    } catch (error) {
            container.innerHTML = `<div class="alert alert-danger">${error.message}</div>`;
        }
    }

    // --- START REFACTOR: NEW AND MODIFIED FUNCTIONS ---

    /**
     * Sets the visual 'active' state on the unit list menu.
     * Used by the gradebook filter.
     * @param {string} unitId The ID of the unit to highlight.
     */
    function setActiveUnitFilter(unitId) {
            // Update left sidebar visual state
        document.querySelectorAll('#unitList a').forEach(a => {
            a.classList.toggle('active', a.dataset.unitId === unitId);
        });
    }

    /**
     * Shows/hides gradebook columns based on the selected unit ID.
     * @param {string} unitId The ID of the unit to show.
     */
    function filterGradebookColumns(unitId) {
        const table = document.getElementById('gradebook-table');
        if (!table) return;

        // 1. Reset: Hide all unit-specific columns first
        table.querySelectorAll('.unit-column').forEach(col => {
            col.style.display = 'none';
        });
        
        // 2. Show the selected unit's columns
        const selector = `.unit-id-${unitId}`;
        table.querySelectorAll(selector).forEach(col => {
            col.style.display = 'table-cell';
        });
    }
    
    /**
     * [FINAL CORRECTED VERSION] Renders the gradebook table with the "Unit Summary"
     * column correctly placed at the END of each unit's item list.
     */
function renderGradebookTable(data, container, unitIdToSelect) {
        if (!data.students || data.students.length === 0) {
            container.innerHTML = `<div class="text-center text-muted py-5"><h4><i class="bi bi-people"></i> ไม่มีข้อมูลนักเรียนในห้องเรียนนี้</h4></div>`;
            return;
        }

        const template = document.getElementById('gradebook-template').content.cloneNode(true);
        const table = template.querySelector('#gradebook-table');
        table.dataset.courseId = data.course_id;
        table.dataset.grandMaxScore = data.grand_max_score || 100;
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('#gradebook-body');

        // --- 1. BUILD HEADER (<thead>) ---
        const headerRow = document.createElement('tr');
        headerRow.innerHTML = '<th rowspan="2" class="align-middle text-center">นักเรียน</th>';
        let subHeaderRowHtml = '';

        // Helper function to create toggle switches
        const createToggleSwitches = (itemId, groupToggle = true, allToggle = true) => {
            let html = '<div class="d-flex justify-content-center small mt-1">';
            if (groupToggle) {
                html += '<div class="form-check form-switch form-check-inline me-2">' +
                        '<input class="form-check-input propagation-toggle group-toggle" type="checkbox" role="switch" title="เปิด/ปิดการให้คะแนนแบบกลุ่ม" data-item-id="' + itemId + '" data-mode="group">' +
                        '<label class="form-check-label">กลุ่ม</label>' +
                    '</div>';
            }
            if (allToggle) {
                html += '<div class="form-check form-switch form-check-inline">' +
                        '<input class="form-check-input propagation-toggle all-toggle" type="checkbox" role="switch" title="เปิด/ปิดการให้คะแนนทั้งหมด" data-item-id="' + itemId + '" data-mode="all">' +
                        '<label class="form-check-label">ทั้งหมด</label>' +
                    '</div>';
            }
            html += '</div>';
            return html;
        };

        // Step 1.1: Build Graded Items Section Header (คงเดิม)
        for (const unitTitle in data.grouped_graded_items) {
            const items = data.grouped_graded_items[unitTitle];
            if (!items || items.length === 0) continue;
            const unitId = items[0].learning_unit_id;
            headerRow.innerHTML += `<th colspan="${items.length + 1}" class="text-center unit-column unit-id-${unitId}">${unitTitle}</th>`;
            
            items.forEach(item => {
                subHeaderRowHtml += `<th class="text-nowrap text-center unit-column unit-id-${unitId}">
                                        ${item.name}<br><small class="text-muted">(${item.max_score || 0})</small>
                                        ${createToggleSwitches(item.id)}
                                    </th>`;
            });
            subHeaderRowHtml += `<th class="text-nowrap text-center unit-column unit-id-${unitId} table-primary">สรุปหน่วย</th>`;
        }

        // =========================================================================
        // --- START REVISED SECTION ---
        // Step 1.2: Build Qualitative Assessment Section Header (ฉบับปรับปรุง)
        data.qualitative_assessment_data.forEach(template => {
            template.main_topics.forEach(mainTopic => {
                const subTopics = mainTopic.selected_sub_topics;
                const unitId = mainTopic.learning_unit_id;
                
                if (subTopics && subTopics.length > 0) {
                    // กรณีมีหัวข้อย่อย: สร้างคอลัมน์ "สรุป" และ "หัวข้อย่อย" ให้สูงเต็ม 2 แถว
                    headerRow.innerHTML += `<th rowspan="2" class="text-nowrap align-middle text-center unit-column unit-id-${unitId} table-info">
                                                สรุป<br><small>${mainTopic.main_topic_name}</small>
                                                ${createToggleSwitches(mainTopic.main_topic_id)}
                                            </th>`;
                    subTopics.forEach(sub => {
                        headerRow.innerHTML += `<th rowspan="2" class="text-nowrap align-middle text-center unit-column unit-id-${unitId}">
                                                    ${sub.name}
                                                </th>`;
                    });
                } else {
                    // กรณีไม่มีหัวข้อย่อย: สร้างแค่คอลัมน์เดียวให้สูงเต็ม 2 แถว
                    headerRow.innerHTML += `<th rowspan="2" class="text-nowrap align-middle text-center unit-column unit-id-${unitId} table-info">
                                                <small>${mainTopic.main_topic_name}</small>
                                                ${createToggleSwitches(mainTopic.main_topic_id)}
                                            </th>`;
                }
            });
        });
        // --- END REVISED SECTION ---
        // =========================================================================

        // Step 1.3: Build Exams & Final Summary Header (คงเดิม)
        let finalColspan = 4;
        if (data.is_midterm_enabled) finalColspan++;
        if (data.is_final_enabled) finalColspan++;
        headerRow.innerHTML += `<th colspan="${finalColspan}" class="text-center">สรุปผลการเรียน</th>`;

        subHeaderRowHtml += `<th class="text-nowrap text-center">คะแนนเก็บ</th>`;
        if (data.is_midterm_enabled) {
            subHeaderRowHtml += `<th class="text-nowrap text-center">กลางภาค (${data.total_midterm_max_score || 0}) ${createToggleSwitches('midterm', false)}</th>`;
        }
        if (data.is_final_enabled) {
            subHeaderRowHtml += `<th class="text-nowrap text-center">ปลายภาค (${data.total_final_max_score || 0}) ${createToggleSwitches('final', false)}</th>`;
        }
        subHeaderRowHtml += `<th class="text-nowrap text-center">คะแนนจริง</th><th class="text-nowrap text-center">รวมคะแนน (100)</th><th class="text-nowrap text-center">เกรด</th>`;

        thead.innerHTML = '';
        thead.appendChild(headerRow);
        const subHeader = document.createElement('tr');
        subHeader.innerHTML = subHeaderRowHtml;
        thead.appendChild(subHeader);

        // --- 2. BUILD BODY (<tbody>) in the same sequence as the header ---
        // (ส่วนนี้ทั้งหมดคงไว้เหมือนเดิม ไม่มีการเปลี่ยนแปลง)
        data.students.forEach(student => {
            const studentRow = document.createElement('tr');
            studentRow.dataset.studentId = student.id;
            let groupIds = {};
            const groups = data.groups || [];
            for (const unitId in data.unit_group_map) {
                if (data.unit_group_map[unitId] && data.unit_group_map[unitId][student.id]) {
                    const group_name = data.unit_group_map[unitId][student.id];
                    const group = groups.find(g => g.name === group_name && g.learning_unit_id == unitId);
                    if (group) {
                        groupIds[unitId] = group.id;
                    }
                }
            }
            studentRow.dataset.groupIds = JSON.stringify(groupIds);
            let rowHtml = `<td class="text-nowrap student-cell">${student.roll_number}. ${student.student_id} ${student.name_prefix || ''}${student.first_name} ${student.last_name}<span class="student-alerts-container">${renderAlerts(student.alerts)}</span></td>`;
            for (const unitTitle in data.grouped_graded_items) {
                const items = data.grouped_graded_items[unitTitle];
                if (!items || items.length === 0) continue;
                const unitId = items[0].learning_unit_id;
                const unitTotalMaxScore = items.reduce((s, it) => s + (parseFloat(it.max_score) || 0), 0);
                items.forEach(item => {
                    let inputHtml = '';
                    const studentGroupId = groupIds[unitId] || null;
                    if (item.is_group_assignment && studentGroupId) {
                        const scoreKey = `${student.id}-${item.id}`;
                        const score = data.scores[scoreKey]?.score ?? '';
                        inputHtml = `<input type="number" class="form-control form-control-sm text-center score-input is-group-score" 
                                            data-item-id="${item.id}" 
                                            data-group-id="${studentGroupId}"
                                            data-unit-id="${unitId}"
                                            data-max-score="${item.max_score || 0}"
                                            value="${score}" max="${item.max_score || 0}" min="0">`;
                    } else {
                        const scoreKey = `${student.id}-${item.id}`;
                        const score = data.scores[scoreKey]?.score ?? '';
                        inputHtml = `<input type="number" class="form-control form-control-sm text-center score-input" 
                                            data-item-id="${item.id}" value="${score}" 
                                            max="${item.max_score || 0}" min="0"
                                            data-unit-id="${unitId}"
                                            data-max-score="${item.max_score || 0}">`;
                    }
                    rowHtml += `<td class="unit-column unit-id-${unitId}">${inputHtml}</td>`;
                });
                rowHtml += `<td class="unit-column unit-id-${unitId}"><input type="number" class="form-control form-control-sm text-center unit-summary-input" data-unit-id="${unitId}" data-unit-total-max-score="${unitTotalMaxScore}" max="${unitTotalMaxScore}"></td>`;
            }
            data.qualitative_assessment_data.forEach(template => {
                const rubrics = template.rubrics;
                template.main_topics.forEach(mainTopic => {
                    const subTopics = mainTopic.selected_sub_topics;
                    const unitId = mainTopic.learning_unit_id;
                    let selectOptions = '<option value=""></option>';
                    if (rubrics) {
                        rubrics.forEach(rubric => {
                            selectOptions += `<option value="${rubric.value}">${rubric.label}</option>`;
                        });
                    }
                    if (subTopics && subTopics.length > 0) {
                        const summaryScoreKey = `${student.id}-q-${mainTopic.main_topic_id}`;
                        const summaryScore = data.scores[summaryScoreKey]?.score ?? '';
                        rowHtml += `<td class="unit-column unit-id-${unitId}">
                                        <select class="form-select form-select-sm text-center qualitative-main-summary" 
                                                data-main-id="${mainTopic.main_topic_id}" 
                                                data-topic-id="${mainTopic.main_topic_id}" 
                                                data-initial-score="${summaryScore}">
                                            ${selectOptions}
                                        </select>
                                    </td>`;
                        subTopics.forEach(sub => {
                            const scoreKey = `${student.id}-q-${sub.id}`;
                            const score = data.scores[scoreKey]?.score ?? '';
                            rowHtml += `<td class="unit-column unit-id-${unitId}">
                                            <select class="form-select form-select-sm text-center qualitative-select" 
                                                    data-main-id="${mainTopic.main_topic_id}" 
                                                    data-topic-id="${sub.id}" 
                                                    data-course-id="${data.course_id}" 
                                                    data-initial-score="${score}">
                                                ${selectOptions}
                                            </select>
                                        </td>`;
                        });
                    } else {
                        const mainScoreKey = `${student.id}-q-${mainTopic.main_topic_id}`;
                        const mainScore = data.scores[mainScoreKey]?.score ?? '';
                        rowHtml += `<td class="unit-column unit-id-${unitId}"><select class="form-select form-control-sm text-center qualitative-select" data-topic-id="${mainTopic.main_topic_id}" data-initial-score="${mainScore}">${selectOptions}</select></td>`;
                    }
                });
            });
            rowHtml += `<td><span class="collected-score-display fw-bold">0</span></td>`;
            if (data.is_midterm_enabled) {
                rowHtml += `<td><input type="number" class="form-control form-control-sm text-center exam-input" data-exam-type="midterm" value="${student.midterm_score ?? ''}" max="${data.total_midterm_max_score || 0}"></td>`;
            }
            if (data.is_final_enabled) {
                rowHtml += `<td><input type="number" class="form-control form-control-sm text-center exam-input" data-exam-type="final" value="${student.final_score ?? ''}" max="${data.total_final_max_score || 0}"></td>`;
            }
            rowHtml += `
                <td><span class="total-score-display fw-bold">0</span></td>
                <td><span class="percentage-display fw-bold">0</span></td>
                <td><span class="grade-display fw-bold">-</span></td>
            `;
            studentRow.innerHTML = rowHtml;
            tbody.appendChild(studentRow);
            updateStudentRowTotals(studentRow);
        });

        container.innerHTML = '';
        container.appendChild(template);
        setupGradebookEventListeners(table, data);

        table.querySelectorAll('select[data-initial-score]').forEach(select => {
            const initialValue = select.dataset.initialScore;
            if (initialValue !== '') {
                select.value = initialValue;
            }
        });

        const unitValues = Object.values(data.grouped_graded_items);
        const firstUnitId = (unitValues.length > 0 && unitValues[0].length > 0) 
                        ? unitValues[0][0].learning_unit_id 
                        : null;

        const idToShow = String(unitIdToSelect || firstUnitId || '');
        if (idToShow) {
            filterGradebookColumns(idToShow);
            setActiveUnitFilter(idToShow);
        }
    }
    
    function updateStudentRowTotals(rowElement) {
        // เพิ่มการตรวจสอบตั้งแต่แรกว่า rowElement ไม่ใช่ null
        if (!rowElement) {
            console.warn("updateStudentRowTotals ถูกเรียกโดยไม่มี rowElement");
            return;
        }        
        // Part 1: Per-unit summary calculation
        // คำนวณคะแนนสรุปของแต่ละหน่วยการเรียนรู้
        rowElement.querySelectorAll('.unit-summary-input').forEach(summaryInput => {
            const unitId = summaryInput.dataset.unitId;
            let currentUnitSum = 0;
            rowElement.querySelectorAll(`.score-input[data-unit-id="${unitId}"]`).forEach(itemInput => {
                currentUnitSum += parseFloat(itemInput.value) || 0;
            });
            summaryInput.value = currentUnitSum.toFixed(2).replace(/\.00$/, '');
        });

        // Part 2: Calculate final summary scores
        // คำนวณคะแนนรวมทั้งหมดที่ส่วนท้ายของตาราง
        let collectedScore = 0;
        rowElement.querySelectorAll('.score-input').forEach(input => {
            collectedScore += parseFloat(input.value) || 0;
        });
        const midtermInput = rowElement.querySelector('.exam-input[data-exam-type="midterm"]');
        const finalInput = rowElement.querySelector('.exam-input[data-exam-type="final"]');
        const midtermScore = midtermInput ? (parseFloat(midtermInput.value) || 0) : 0;
        const finalScore = finalInput ? (parseFloat(finalInput.value) || 0) : 0;
        let overallTotalScore = collectedScore + midtermScore + finalScore;

        // Part 3: Write back to final summary displays
        const collectedDisplay = rowElement.querySelector('.collected-score-display');
        if (collectedDisplay) {
            collectedDisplay.textContent = collectedScore.toFixed(2).replace(/\.00$/, '');
        }

        const totalDisplay = rowElement.querySelector('.total-score-display');
        if (totalDisplay) {
            totalDisplay.textContent = overallTotalScore.toFixed(2).replace(/\.00$/, '');
        }

        // Part 4: Grade Display Logic
        const table = rowElement.closest('table');
        const grandMax = parseFloat(table?.dataset?.grandMaxScore) || 100;
        let percent = (grandMax > 0) ? (overallTotalScore / grandMax) * 100 : 0;
        
        // นี่คือบรรทัดที่เคยเกิดปัญหา เราจะตรวจสอบก่อน
        const percentageDisplay = rowElement.querySelector('.percentage-display');
        if (percentageDisplay) {
            percentageDisplay.textContent = `${percent.toFixed(0)}%`;
        }

        // Helper function (คงเดิม)
        function mapToGrade(p) {
            if (p >= 80) return '4'; if (p >= 75) return '3.5'; if (p >= 70) return '3';
            if (p >= 65) return '2.5'; if (p >= 60) return '2'; if (p >= 55) return '1.5';
            if (p >= 50) return '1'; return '0';
        }

        // Get display elements and alert status
        const gradeDisplay = rowElement.querySelector('.grade-display');
        const alertContainer = rowElement.querySelector('.student-alerts-container');
        const alertsText = alertContainer ? alertContainer.textContent : '';

        // ตรวจสอบ gradeDisplay ก่อนใช้งาน
        if (gradeDisplay) {
            if (alertsText.includes('ร')) {
                gradeDisplay.textContent = 'ร';
                gradeDisplay.className = 'grade-display fw-bold text-danger';
            } 
            else if (alertsText.includes('0')) {
                gradeDisplay.textContent = '0';
                gradeDisplay.className = 'grade-display fw-bold text-danger';
            } 
            else {
                const grade = mapToGrade(percent);
                gradeDisplay.textContent = grade;
                gradeDisplay.className = (grade === '0') ? 'grade-display fw-bold text-danger' : 'grade-display fw-bold';
            }
        }
        // --- END: CORRECTLY ORDERED GRADE/ALERT LOGIC ---
    }

    /**
     * Fetches and displays content for a specific tab pane.
     * @param {string|null} unitId The ID of the current unit, or null for plan-wide tabs.
     * @param {string} paneId The ID of the tab pane to load content into (e.g., 'plan-content').
     */
    async function loadTabContent(unitId, paneId) {
        // "แผนที่" ที่ใช้ ID ของ Pane เป็น Key
        const tabEndpoints = {
            'plan-content': `/teacher/api/units/${unitId}/plan`,
            'assessment-content': `/teacher/api/units/${unitId}/assessment-setup`,
            'gradebook-content': `/teacher/api/plan/${planId}/gradebook-ui`,
            'reflection-content': `/teacher/api/units/${unitId}/reflection-tab`
        };
        
        const apiUrl = tabEndpoints[paneId];
        const targetPane = document.getElementById(paneId);

        if (!targetPane) {
            console.error(`Tab pane for id '${paneId}' not found.`);
            return;
        }

        // ลบข้อความ "กรุณาเลือกหน่วย..." เริ่มต้นทิ้งไปเสมอเมื่อมีการโหลดเนื้อหาแท็บ
        document.getElementById('initial-message')?.remove();        

        if (!apiUrl) {
            targetPane.innerHTML = `<div class="p-5 text-center text-muted">ฟีเจอร์นี้กำลังอยู่ในระหว่างการพัฒนา...</div>`;
            return;
        }

        const loadingOverlay = document.getElementById('workspaceTabsContent');
        try {
            loadingOverlay.classList.add('loading');
            const response = await fetch(apiUrl);
            if (!response.ok) throw new Error(`Network response was not ok`);
            
            targetPane.innerHTML = await response.text();

            // เรียกใช้ฟังก์ชันติดตั้งของแต่ละแท็บหลังจากโหลด UI เสร็จ
            if (paneId === 'plan-content') {
                initializeLessonPlanTab(unitId);
            } else if (paneId === 'assessment-content') {
                initializeAssessmentSetupTab();
            } else if (paneId === 'gradebook-content') {
                initializeGradebookTab();
            } else if (paneId === 'reflection-content') {
                initializeReflectionTab();
            }

        } catch (error) {
            targetPane.innerHTML = `<div class="alert alert-danger">เกิดข้อผิดพลาดในการโหลดเนื้อหา: ${error.message}</div>`;
            console.error('Failed to load tab content:', error);
        } finally {
            // **สำคัญ:** ลบ Overlay ออกเสมอ ไม่ว่าจะสำเร็จหรือล้มเหลว
            loadingOverlay.classList.remove('loading');
        }
    }

    // --- TAB-SPECIFIC INITIALIZERS ---

    /**
     * Initializes TomSelect and form submission for the Lesson Plan tab.
     * @param {string} unitId The current unit ID.
     */
    function initializeLessonPlanTab(unitId) {
        const hoursInput = workspaceTabsContent.querySelector('.learning-unit-hours-input');
        if (hoursInput) {
            unitHoursData[unitId] = parseInt(hoursInput.value, 10) || 0;
        }
        updateCumulativePeriods();        

        const planForm = document.getElementById('lessonPlanForm');
        if (planForm) {
            planForm.action = `/teacher/api/units/${unitId}/plan/save`;
            planForm.method = 'POST';
            planForm.addEventListener('submit', handlePlanFormSubmit);
        }

        const selector = document.getElementById('indicator-selector');
        if (!selector) return;

        const initialOptionsJSON = selector.dataset.initialOptions || '[]';
        const initialOptions = JSON.parse(initialOptionsJSON);
        const initialItemIds = initialOptions.map(opt => opt.id);
        if (hoursInput) {
            // Update the central data store with the value loaded from the server
            unitHoursData[unitId] = parseInt(hoursInput.value, 10) || 0;
        }

        if (tomSelect) {
            tomSelect.destroy();
        }

        tomSelect = new TomSelect(selector, {
            valueField: 'id',
            labelField: 'text',
            searchField: ['text'],
            create: true,
            options: initialOptions,
            items: initialItemIds,

            // Replace 'create: true' and 'onCreate' with a single 'create' function
            create: function(input, callback) {
                console.log("create function triggered with input:", input); // Debug log

                Swal.fire({
                    title: 'สร้างตัวชี้วัดใหม่',
                    html: `
                        <input id="swal-indicator-code" class="swal2-input" placeholder="รหัสตัวชี้วัด (เช่น ม.3/9)">
                        <textarea id="swal-indicator-desc" class="swal2-textarea" placeholder="รายละเอียดตัวชี้วัด">${input}</textarea>
                    `,
                    confirmButtonText: 'บันทึก',
                    showCancelButton: true,
                    cancelButtonText: 'ยกเลิก',
                    focusConfirm: false,
                    preConfirm: () => {
                        const code = Swal.getPopup().querySelector('#swal-indicator-code').value;
                        const desc = Swal.getPopup().querySelector('#swal-indicator-desc').value;
                        if (!code || !desc) {
                            Swal.showValidationMessage(`กรุณากรอกข้อมูลให้ครบถ้วน`);
                        }
                        return { code: code, description: desc };
                    }
                }).then((result) => {
                    if (result.isConfirmed) {
                        fetch(addIndicatorUrl, {
                            method: 'POST',
                            headers: { 
                                'Content-Type': 'application/json', 
                                'X-CSRFToken': csrfToken 
                            },
                            body: JSON.stringify({ ...result.value, plan_id: planId })
                        })
                        .then(response => response.json())
                        .then(data => {
                            console.log("API response:", data);
                            if (data.status === 'success' && data.indicator && data.indicator.id) {
                                // On success, pass the complete new option object to the callback
                                callback(data.indicator);
                            } else {
                                Swal.fire('เกิดข้อผิดพลาด!', data.message || 'ไม่สามารถสร้างตัวชี้วัดได้', 'error');
                                // On failure, call callback without arguments to cancel creation
                                callback();
                            }
                        });
                    } else {
                        // If user cancels the Swal modal, cancel the creation
                        callback();
                    }
                });
            },
                        
            load: function(query, callback) {
                if (query.length < 2) return callback();
                fetch(`{{ url_for("teacher.search_indicators") }}?q=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(callback)
                    .catch(() => callback());
            },
            createFilter: input => input.length >= 3,
            render: {
                item: function(data, escape) {
                    return `<div>[${escape(data.standard_code || '')}] ${escape(data.indicator_code || '')}</div>`;
                },
                option: (data, escape) => `<div><strong>${escape(data.standard_code)} ${escape(data.indicator_code)}</strong>: <span class="text-muted">${escape(data.indicator_desc)}</span></div>`,
                option_create: (data, escape) => `<div class="create">เพิ่มตัวชี้วัดใหม่: <strong>${escape(data.input)}</strong>&hellip;</div>`,
            },
            onInitialize: function() { renderSelectedIndicators(this); },
            onItemAdd: function() { this.setTextboxValue(''); this.blur(); renderSelectedIndicators(this); },
            onItemRemove: function() { renderSelectedIndicators(this); },
            
        });

        document.getElementById('subUnitEditForm').addEventListener('submit', handleSubUnitFormSubmit);
    }

    /**
     * Initializes all event listeners for the Assessment Setup tab content.
     */
    function initializeAssessmentSetupTab() {
        // Sync accordion state back to the main sidebar menu
        const accordion = document.getElementById('learningUnitsAccordion');
        if (accordion) {
            accordion.addEventListener('show.bs.collapse', e => {
                const unitId = e.target.id.replace('collapse-unit-', '');
                if (unitId && unitId !== activeUnitId) {
                    setActiveUnit(unitId); // This keeps UI in sync
                }
            });
        }

        // --- MODIFIED SECTION: Open the active unit's accordion instantly (no animation) ---
        // First, ensure all accordions are reset to a closed state
        document.querySelectorAll('#learningUnitsAccordion .accordion-collapse').forEach(el => {
            el.classList.remove('show');
        });
        document.querySelectorAll('#learningUnitsAccordion .accordion-button').forEach(btn => {
            btn.classList.add('collapsed');
            btn.setAttribute('aria-expanded', 'false');
        });

        // Then, find the target accordion and button for the active unit
        const targetCollapseEl = document.getElementById(`collapse-unit-${activeUnitId}`);
        const targetButton = document.querySelector(`button[data-bs-target="#collapse-unit-${activeUnitId}"]`);
        
        // Manually set the classes to make them appear 'open' without animation
        if (targetCollapseEl && targetButton) {
            targetCollapseEl.classList.add('show');
            targetButton.classList.remove('collapsed');
            targetButton.setAttribute('aria-expanded', 'true');
        }
        // --- END OF MODIFIED SECTION ---

        // Setup graded item modal listeners
        setupGradedItemModal();
        
        // Setup ratio target modal listeners
        setupRatioTargetModal();
        loadRatioTarget().then(() => {
            updateSummaryPanel();
        });
    }

    /**
     * Initializes the entire Reflection Tab, including fetching dashboard data
     * and setting up the dual-mode logging system.
     */
        const renderDashboard = (dashboardData, unitMaxScore) => {
        const tbody = wrapper.querySelector('#dashboard-table-body');
        const tfoot = wrapper.querySelector('#dashboard-table-foot');
        tbody.innerHTML = '';
        tfoot.innerHTML = '';

        let totalStudents = 0, totalIncomplete = 0;
        let totalScoresSum = 0; // Changed variable name for clarity
        let totalScoredStudents = 0; // Count students with scores for weighted avg
        let totalDist = { excellent: 0, good: 0, fair: 0, improve: 0 };

        dashboardData.forEach(room => {
            const studentsWithScores = room.student_count - room.incomplete;
            totalStudents += room.student_count;
            totalIncomplete += room.incomplete;
            totalScoresSum += (room.avg_score * studentsWithScores);
            totalScoredStudents += studentsWithScores;

            Object.keys(totalDist).forEach(key => totalDist[key] += room.distribution[key]);

            tbody.innerHTML += `
                <tr>
                    <td class="text-start">${room.name}</td>
                    <td>${room.student_count}</td>
                    <td>${unitMaxScore}</td>
                    <td>${room.avg_score} (${unitMaxScore > 0 ? Math.round(room.avg_score / unitMaxScore * 100) : 0}%)</td>
                    <td>${room.sd}</td>
                    <td>${room.distribution.excellent}</td>
                    <td>${room.distribution.good}</td>
                    <td>${room.distribution.fair}</td>
                    <td>${room.distribution.improve}</td>
                    <td>${room.incomplete}</td>
                </tr>
            `;
        });
        
        const overallAvg = totalScoredStudents > 0 ? (totalScoresSum / totalScoredStudents) : 0;
        tfoot.innerHTML = `
            <tr class="table-primary fw-bold">
                <td>สรุปทั้งหมด</td>
                <td>${totalStudents}</td>
                <td>${unitMaxScore}</td>
                <td>${overallAvg.toFixed(2)} (${unitMaxScore > 0 ? Math.round(overallAvg / unitMaxScore * 100) : 0}%)</td>
                <td>-</td>
                <td>${totalDist.excellent}</td>
                <td>${totalDist.good}</td>
                <td>${totalDist.fair}</td>
                <td>${totalDist.improve}</td>
                <td>${totalIncomplete}</td>
            </tr>
        `;
    };

    // --- AJAX Save Function and Event Listener Setup ---
    const setupLoggingSystem = (logData, dashboardData) => {
        const overallForm = wrapper.querySelector('#overall-log-form');
        const navContainer = wrapper.querySelector('#per-room-log-nav');
        const contentContainer = wrapper.querySelector('#per-room-log-content');
        
        // 1. Populate Overall Log
        overallForm.querySelector('#log_content_overall').value = logData.overall.log_content;
        overallForm.querySelector('#problems_obstacles').value = logData.overall.problems_obstacles;
        overallForm.querySelector('#solutions').value = logData.overall.solutions;

        // 2. Populate Per-Room Logs UI
        navContainer.innerHTML = '';
        contentContainer.innerHTML = '';
        dashboardData.forEach((room, index) => {
            const roomLog = logData.per_room[room.id] || { log_content: '' };
            navContainer.innerHTML += `
                <button type="button" class="list-group-item list-group-item-action ${index === 0 ? 'active' : ''}" data-room-id="${room.id}">
                    ${room.name}
                </button>`;
            contentContainer.innerHTML += `
                <div class="per-room-log-pane ${index === 0 ? '' : 'd-none'}" id="log-pane-${room.id}">
                     <label for="log-room-${room.id}" class="form-label small text-muted">บันทึกสำหรับห้อง ${room.name}:</label>
                     <textarea class="form-control per-room-textarea" id="log-room-${room.id}" data-room-id="${room.id}" rows="4">${roomLog.log_content}</textarea>
                </div>`;
        });

        // 3. Setup Event Listeners
        overallForm.addEventListener('input', (e) => handleSave(e.target));
        
        navContainer.addEventListener('click', e => {
            if (e.target.matches('button')) {
                navContainer.querySelectorAll('button').forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                contentContainer.querySelectorAll('.per-room-log-pane').forEach(pane => pane.classList.add('d-none'));
                contentContainer.querySelector(`#log-pane-${e.target.dataset.roomId}`).classList.remove('d-none');
            }
        });

        contentContainer.addEventListener('input', e => {
             if (e.target.matches('.per-room-textarea')) {
                handleSave(e.target);
             }
        });
    };
    
    // 4. The Core AJAX Save Handler
    const handleSave = (element) => {
        clearTimeout(reflectionSaveDebounce);
        statusIndicator.textContent = 'กำลังพิมพ์...';
        
        reflectionSaveDebounce = setTimeout(async () => {
            statusIndicator.innerHTML = '<div class="spinner-border spinner-border-sm me-2" role="status"></div>กำลังบันทึก...';
            
            const isPerRoom = element.dataset.roomId;
            let payload = {};
            
            if (isPerRoom) {
                // สร้าง payload สำหรับบันทึกรายห้อง
                payload = {
                    classroom_id: element.dataset.roomId,
                    log_content: element.value
                };
            } else {
                // สร้าง payload สำหรับบันทึกภาพรวม
                const overallForm = wrapper.querySelector('#overall-log-form');
                payload = {
                    classroom_id: null,
                    log_content: overallForm.querySelector('#log_content_overall').value,
                    problems_obstacles: overallForm.querySelector('#problems_obstacles').value,
                    solutions: overallForm.querySelector('#solutions').value
                }
            }

            try {
                // ส่งข้อมูล AJAX ไปยัง Backend
                const response = await fetch(`/teacher/api/log/unit/${unitId}`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken // ตรวจสอบว่ามี csrfToken ใน scope นี้
                    },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error('Save failed');
                
                // อัปเดตสถานะเมื่อบันทึกสำเร็จ
                const now = new Date();
                const timeString = now.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
                statusIndicator.textContent = 'บันทึกฉบับร่างล่าสุดเมื่อ ' + timeString + ' น.';

            } catch (error) {
                statusIndicator.textContent = 'เกิดข้อผิดพลาดในการบันทึก!';
                console.error('Save error:', error);
            }

        }, 1500); // ตั้งเวลาหน่วง 1.5 วินาที
    };

    // Initial load
    loadDashboardAndLogs();
}
    }

    // --- HANDLER FUNCTIONS ---
    // --- ฟังก์ชันใหม่สำหรับจัดการ Sub-Unit ---
    function renderSubUnit(subUnit) {
        return `
            <div class="card mb-2" id="subunit-card-${subUnit.id}">
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h6 class="card-title mb-1">
                                <span class="badge bg-primary me-2">ชั่วโมงที่ ${subUnit.hour_sequence}</span>
                                <span class="subunit-title">${subUnit.title}</span>
                            </h6>
                            <p class="card-text text-muted small subunit-activities">${subUnit.activities || ''}</p>
                        </div>
                        <div>
                            <button class="btn btn-sm btn-outline-secondary edit-subunit-btn" data-subunit-id="${subUnit.id}">
                                <i class="bi bi-pencil"></i> แก้ไข
                            </button>
                            <button class="btn btn-sm btn-outline-danger delete-subunit-btn" data-subunit-id="${subUnit.id}">
                                <i class="bi bi-trash"></i> ลบ
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async function handleAddSubUnit(button) {
        const unitId = button.dataset.unitId;
        const response = await fetch(`/teacher/api/units/${unitId}/sub_units`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken }
        });
        if (response.ok) {
            const newSubUnit = await response.json();
            document.getElementById('no-subunits-placeholder')?.remove();
            document.getElementById('sub-units-list').insertAdjacentHTML('beforeend', renderSubUnit(newSubUnit));
            
            const list = document.getElementById('sub-units-list');
            const unitHours = parseInt(button.dataset.unitHours, 10);
            if (list.children.length >= unitHours) {
                button.disabled = true;
            }
        } else {
            Swal.fire('เกิดข้อผิดพลาด', 'ไม่สามารถเพิ่มแผนรายชั่วโมงได้', 'error');
        }
    }

    async function handleEditSubUnit(button) {
        const subUnitId = button.dataset.subunitId;

        // Fetch sub-unit details AND graded item options for the parent unit concurrently
        const [subUnitResponse, gradedItemsResponse] = await Promise.all([
            fetch(`/teacher/api/sub_units/${subUnitId}`),
            fetch(`/teacher/api/units/${activeUnitId}/graded-items-for-selection`)
        ]);

        if (!subUnitResponse.ok || !gradedItemsResponse.ok) {
            Swal.fire('เกิดข้อผิดพลาด', 'ไม่สามารถโหลดข้อมูลสำหรับแก้ไขได้', 'error');
            return;
        }

        const data = await subUnitResponse.json();
        const gradedItemsOptions = await gradedItemsResponse.json();
        
        const modal = document.getElementById('subUnitEditModal');
        modal.querySelector('#modal-subunit-id').value = data.id;
        modal.querySelector('#modal-subunit-title').value = data.title;
        modal.querySelector('#modal-subunit-activities').value = data.activities;

        // Setup TomSelect for Indicators (no changes here)
        if (subUnitIndicatorsTomSelect) subUnitIndicatorsTomSelect.destroy();
        subUnitIndicatorsTomSelect = new TomSelect('#modal-subunit-indicators', {
            valueField: 'id',
            labelField: 'text',
            searchField: ['text'],
            options: tomSelect.options, // Reuse options from the main selector
            items: data.indicator_ids
        });

        // Setup TomSelect for Graded Items using fetched options
        if (subUnitGradedItemsTomSelect) subUnitGradedItemsTomSelect.destroy();
        subUnitGradedItemsTomSelect = new TomSelect('#modal-subunit-graded-items', {
            valueField: 'id',
            labelField: 'name',
            searchField: ['name'],
            options: gradedItemsOptions, // Use the options fetched from our new API
            items: data.graded_item_ids
        });

        subUnitEditModal.show();
    }

    async function handleSubUnitFormSubmit(e) {
        e.preventDefault();
        const subUnitId = this.querySelector('#modal-subunit-id').value;
        const data = {
            title: this.querySelector('#modal-subunit-title').value,
            activities: this.querySelector('#modal-subunit-activities').value,
            indicator_ids: subUnitIndicatorsTomSelect.getValue(),
            graded_item_ids: subUnitGradedItemsTomSelect.getValue()
        };

        const response = await fetch(`/teacher/api/sub_units/${subUnitId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            subUnitEditModal.hide();
            const card = document.getElementById(`subunit-card-${subUnitId}`);
            if (card) {
                card.querySelector('.subunit-title').textContent = data.title;
                card.querySelector('.subunit-activities').textContent = data.activities;
            }
            Swal.fire({ toast: true, position: 'top-end', icon: 'success', title: 'บันทึกสำเร็จ', showConfirmButton: false, timer: 1500 });
        } else {
            Swal.fire('เกิดข้อผิดพลาด', 'ไม่สามารถบันทึกข้อมูลได้', 'error');
        }
    }

    function handleDeleteSubUnit(button) {
        const subUnitId = button.dataset.subunitId;
        Swal.fire({
            title: 'ยืนยันการลบ',
            text: 'คุณแน่ใจหรือไม่ว่าต้องการลบแผนรายชั่วโมงนี้?',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'ใช่, ลบเลย'
        }).then(async result => {
            if (result.isConfirmed) {
                const response = await fetch(`/teacher/api/sub_units/${subUnitId}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                if (response.ok) {
                    document.getElementById(`subunit-card-${subUnitId}`).remove();
                    
                    const addBtn = document.getElementById('add-subunit-btn');
                    const list = document.getElementById('sub-units-list');
                    const unitHours = parseInt(addBtn.dataset.unitHours, 10);
                    if (list.children.length < unitHours) {
                        addBtn.disabled = false;
                    }
                    if (list.children.length === 0) {
                        list.innerHTML = '<p id="no-subunits-placeholder" class="text-muted fst-italic">ยังไม่มีแผนการสอนรายชั่วโมง</p>';
                    }
                } else {
                    Swal.fire('เกิดข้อผิดพลาด', 'ไม่สามารถลบได้', 'error');
                }
            }
        });
    }

    /**
     * Handles changes for exam scores, syncs UI, saves data, and updates summary.
     */
    async function handleExamScoreChange(e) {
        // Find the parent elements for the specific unit being edited
        const unitContainer = e.target.closest('.accordion-collapse');
        if (!unitContainer) return;

        const unitId = unitContainer.id.replace('collapse-unit-', '');

        const midtermSwitch = unitContainer.querySelector('#midterm-switch-' + unitId);
        const finalSwitch = unitContainer.querySelector('#final-switch-' + unitId);
        const midtermInput = unitContainer.querySelector('.exam-score-input[data-exam-type="midterm"]');
        const finalInput = unitContainer.querySelector('.exam-score-input[data-exam-type="final"]');

        // Part 1: Sync UI state immediately
        // Sync UI state
        if (midtermSwitch && midtermInput) {
            midtermInput.disabled = !midtermSwitch.checked;
            if (!midtermSwitch.checked) midtermInput.value = '';
        }
        if (finalSwitch && finalInput) {
            finalInput.disabled = !finalSwitch.checked;
            if (!finalSwitch.checked) finalInput.value = '';
        }


        // Immediately update the summary panel for real-time feedback
        updateSummaryPanel();

        // Part 2: Construct payload and save to server (debounced)
        // Debounced save
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(async () => {
            const payload = {
                midterm_score: midtermSwitch.checked ? (parseFloat(midtermInput.value) || null) : null,
                final_score: finalSwitch.checked ? (parseFloat(finalInput.value) || null) : null
            };

            try {
                const response = await fetch(`/teacher/api/units/${unitId}/exam-scores`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error('Server returned an error');

                const result = await response.json();
                if (result.status === 'success') {
                    // The existing code has a better popup, let's keep it.
                    // No need for a separate success popup here as the logic is handled 
                    // within the original handleExamScoreChange function in the provided HTML file.
                } else {
                    throw new Error(result.message || 'Application error');
                }
            } catch (error) {
                Swal.fire('เกิดข้อผิดพลาด', 'ไม่สามารถบันทึกคะแนนสอบได้', 'error');
                console.error("Save Error:", error);
            }
        }, 500); // 500ms debounce
    }

    async function handleUnitCreate(e) {
        e.preventDefault();
        const title = this.querySelector('#unit-title-input').value.trim();
        if (!title) return Swal.fire('ข้อผิดพลาด', 'ชื่อหน่วยการเรียนรู้ห้ามว่างเปล่า', 'error');

        const createUrl = unitList.dataset.createUnitUrl;
        const response = await fetch(createUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ title: title })
        });
        const data = await response.json();

        if (data.status === 'success') {
            unitFormModal.hide();
            Swal.fire({ icon: 'success', title: 'สำเร็จ!', text: 'สร้างหน่วยใหม่เรียบร้อย', timer: 1500, showConfirmButton: false });

            const newUnitLink = document.createElement('a');
            newUnitLink.href = '#';
            newUnitLink.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
            newUnitLink.dataset.unitId = data.unit.id;
            newUnitLink.dataset.deleteUrl = `/teacher/api/units/${data.unit.id}`;
            newUnitLink.innerHTML = `<span class="unit-title">${data.unit.title}</span>
                                    <button class="btn btn-sm btn-outline-danger delete-unit-btn border-0" title="Delete Unit">
                                        <i class="bi bi-trash"></i>
                                    </button>`;

            document.getElementById('no-units-placeholder')?.remove();
            unitList.appendChild(newUnitLink);
            unitHoursData[data.unit.id] = 0;
            setActiveUnit(data.unit.id.toString());
        } else {
            Swal.fire('เกิดข้อผิดพลาด', data.message || 'ไม่สามารถสร้างหน่วยได้', 'error');
        }
    }

    function handleUnitDelete(unitLink) {
        Swal.fire({
            title: 'ยืนยันการลบ', text: "คุณแน่ใจหรือไม่ว่าต้องการลบหน่วยนี้?", icon: 'warning',
            showCancelButton: true, confirmButtonColor: '#d33',
            cancelButtonText: 'ยกเลิก', confirmButtonText: 'ใช่, ลบเลย'
        }).then(result => {
            if (result.isConfirmed) {
                fetch(unitLink.dataset.deleteUrl, {
                    method: 'DELETE', headers: { 'X-CSRFToken': csrfToken }
                }).then(res => res.json()).then(data => {
                    if (data.status === 'success') {
                        const wasActive = unitLink.dataset.unitId === activeUnitId;
                        unitLink.remove();
                        if (wasActive) {
                            activeUnitId = null;
                            workspaceTabsContent.innerHTML = `<div id="initial-message" class="text-center text-muted py-5">
                                <h4><i class="bi bi-arrow-left-circle"></i> Please select a learning unit</h4>
                                <p>Select a unit from the menu on the left to get started.</p>
                            </div>`;
                        }
                        if (unitList.children.length === 0) {
                            unitList.innerHTML = '<div id="no-units-placeholder" class="list-group-item text-muted text-center">ยังไม่มีหน่วยการเรียนรู้</div>';
                        }
                        Swal.fire({ toast: true, position: 'top-end', icon: 'success', title: 'ลบหน่วยแล้ว', showConfirmButton: false, timer: 2000 });
                    } else {
                        Swal.fire('ผิดพลาด!', data.message, 'error');
                    }
                });
            }
        });
    }

    async function handlePlanFormSubmit(e) {
        e.preventDefault();
        const form = e.target;
        const data = Object.fromEntries(new FormData(form).entries());
        data.indicators = tomSelect ? tomSelect.getValue() : [];

        const response = await fetch(form.action, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
            body: JSON.stringify(data)
        });
        const result = await response.json();

        if (result.status === 'success') {
            Swal.fire({icon: 'success', title: 'บันทึกแล้ว!', text: result.message, timer: 1500, showConfirmButton: false});
            const unitLinkTitle = document.querySelector(`#unitList a[data-unit-id="${activeUnitId}"] .unit-title`);
            if (unitLinkTitle && result.new_title) {
                unitLinkTitle.textContent = result.new_title;
            }
        } else {
            Swal.fire('เกิดข้อผิดพลาด', result.message || 'ไม่สามารถบันทึกแผนได้', 'error');
        }
    }

    function handleGradedItemDelete(itemId) {
        Swal.fire({
            title: 'ยืนยันการลบ',
            text: "คุณแน่ใจหรือไม่ว่าต้องการลบรายการนี้?",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonText: 'ยกเลิก',
            confirmButtonText: 'ใช่, ลบเลย'
        }).then((result) => {
            if (result.isConfirmed) {
                fetch(`/teacher/api/graded-items/${itemId}`, {
                    method: 'DELETE', headers: { 'X-CSRFToken': csrfToken }
                }).then(response => response.json()).then(data => {
                    if (data.status === 'success') {
                        document.getElementById(`graded-item-${itemId}`)?.remove();
                        updateSummaryPanel();
                        Swal.fire('ลบแล้ว!', 'รายการถูกลบออกแล้ว', 'success');
                    } else {
                        Swal.fire('ผิดพลาด!', data.message, 'error');
                    }
                });
            }
        });
    }

    async function openTopicSelectionModal(button) {
        const templateId = button.dataset.templateId;
        const modalEl = document.getElementById('selectTopicsModal');
        modalEl.querySelector('.modal-title').textContent = `เลือกหัวข้อ: ${button.dataset.templateName}`;
        const modalBody = modalEl.querySelector('.modal-body');
        modalBody.innerHTML = '<div class="d-flex justify-content-center p-5"><div class="spinner-border" role="status"></div></div>';

        const saveBtn = modalEl.querySelector('#saveTopicSelectionBtn');
        const saveHandler = async () => {
            const selectedIds = Array.from(modalEl.querySelectorAll('input[type=checkbox]:checked')).map(cb => parseInt(cb.value));
            const response = await fetch(`/teacher/api/units/${activeUnitId}/assessment-items`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({ template_id: templateId, topic_ids: selectedIds })
            });
            const result = await response.json();
            if (result.status === 'success') {
                selectionModal.hide();
                Swal.fire({
                    icon: 'success', 
                    title: 'สำเร็จ', 
                    text: result.message, 
                    timer: 1500, 
                    showConfirmButton: false
                })
                // After the success message closes, reload the assessment tab's content
                // to show the newly saved topics.
                .then(() => {
                    loadTabContent(activeUnitId, 'assessment-content');
                });
            } else {
                Swal.fire('เกิดข้อผิดพลาด', 'ไม่สามารถบันทึกการตั้งค่าได้', 'error');
            }
        };
        const newSaveBtn = saveBtn.cloneNode(true);
        saveBtn.parentNode.replaceChild(newSaveBtn, saveBtn);
        newSaveBtn.addEventListener('click', saveHandler);

        try {
            const [topicsResponse, selectedResponse] = await Promise.all([
                fetch(`/teacher/api/templates/${templateId}/topics-for-selection`),
                fetch(`/teacher/api/units/${activeUnitId}/selected-topics`)
            ]);

            if (!topicsResponse.ok) throw new Error('Could not load topic structure.');
            if (!selectedResponse.ok) throw new Error('Could not load selected topics.');

            const topicTree = await topicsResponse.json();
            const selectedData = await selectedResponse.json();
            const selectedIds = selectedData.selected_ids || [];

            modalBody.innerHTML = buildCheckboxTree(topicTree, selectedIds);
            setupCheckboxLogic(modalBody);
        } catch (error) {
            modalBody.innerHTML = `<div class="alert alert-danger">ไม่สามารถโหลดหัวข้อได้: ${error.message}</div>`;
            console.error(error);
        }
    }

    // --- SETUP HELPER FUNCTIONS (for initializers) ---

    function setupGradedItemModal() {
        const modalEl = document.getElementById('addAssessmentItemModal');
        if (!modalEl) return;
        const itemModal = new bootstrap.Modal(modalEl);
        const itemForm = document.getElementById('addAssessmentItemForm');

        modalEl.addEventListener('show.bs.modal', async function(event) {
            const button = event.relatedTarget;
            const action = button.dataset.action;
            itemForm.reset();
            this.querySelector('.modal-title').textContent = action === 'edit' ? 'แก้ไขรายการคะแนนเก็บ' : 'เพิ่มรายการคะแนนเก็บ';
            itemForm.dataset.action = action;

            if (action === 'edit') {
                const itemId = button.dataset.itemId;
                itemForm.dataset.itemId = itemId;
                const response = await fetch(`/teacher/api/graded-items/${itemId}`);
                if (!response.ok) return;
                const data = await response.json();
                Object.keys(data).forEach(key => {
                    const input = itemForm.querySelector(`[name="${key}"]`);
                    if (input) input.value = data[key];
                });
            } else {
                const unitId = button.dataset.unitId;
                itemForm.dataset.unitId = unitId;
                itemForm.querySelector('#modal-learningUnitId').value = unitId;
            }
        });

        itemForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const action = this.dataset.action;
            const data = Object.fromEntries(new FormData(this).entries());
            const method = action === 'edit' ? 'PUT' : 'POST';
            const url = action === 'edit'
                ? `/teacher/api/graded-items/${this.dataset.itemId}`
                : `/teacher/api/units/${this.dataset.unitId}/graded-items`;

            const response = await fetch(url, {
                method: method,
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify(data)
            });
            const result = await response.json();

            if (result.status === 'success') {
                itemModal.hide();
                Swal.fire({icon: 'success', title: 'สำเร็จ!', text: result.message, timer: 1500, showConfirmButton: false});

                // Refresh the assessment tab to show the new/updated item
                loadTabContent(activeUnitId, 'assessment-content');

            } else {
                Swal.fire('เกิดข้อผิดพลาด', result.message || 'ไม่สามารถบันทึกรายการได้', 'error');
            }
        });
    }

    function setupRatioTargetModal() {
        const modalEl = document.getElementById('ratioTargetModal');
        if (!modalEl) return;
        const ratioModal = new bootstrap.Modal(modalEl);
        const saveBtn = modalEl.querySelector('#saveRatioTargetBtn');
        const deleteBtn = modalEl.querySelector('#deleteRatioTargetBtn');
        const midRatioInput = modalEl.querySelector('#target-mid-ratio');
        const finalRatioInput = modalEl.querySelector('#target-final-ratio');

        const syncInputs = (source, target) => {
            const sourceValue = Math.max(0, Math.min(100, parseInt(source.value) || 0));
            source.value = sourceValue;
            target.value = 100 - sourceValue;
        };
        midRatioInput.addEventListener('input', () => syncInputs(midRatioInput, finalRatioInput));
        finalRatioInput.addEventListener('input', () => syncInputs(finalRatioInput, midRatioInput));

        saveBtn.addEventListener('click', async () => {
            const midVal = parseInt(midRatioInput.value) || 0;
            const finalVal = parseInt(finalRatioInput.value) || 0;
            if (midVal + finalVal !== 100) return Swal.fire('ข้อผิดพลาด', 'ผลรวมของสัดส่วนต้องเป็น 100', 'error');

            const response = await fetch(`/teacher/api/plan/${planId}/ratio-target`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({ mid_ratio: midVal, final_ratio: finalVal })
            });

            if (response.ok) {
                targetMidRatio = midVal;
                targetFinalRatio = finalVal;
                isTargetSetByUser = true;
                ratioModal.hide();
                updateSummaryPanel();
            } else {
                Swal.fire('เกิดข้อผิดพลาด', 'ไม่สามารถบันทึกสัดส่วนเป้าหมายได้', 'error');
            }
        });

        deleteBtn.addEventListener('click', async () => {
            const response = await fetch(`/teacher/api/plan/${planId}/ratio-target`, {
                method: 'DELETE',
                headers: {'X-CSRFToken': csrfToken}
            });

            if (response.ok) {
                // Reset client-side state
                isTargetSetByUser = false;
                targetMidRatio = 80; // Reset to default
                targetFinalRatio = 20; // Reset to default
                midRatioInput.value = 80; // Reset input in modal
                finalRatioInput.value = 20; // Reset input in modal

                ratioModal.hide();
                updateSummaryPanel(); // Refresh the summary panel to hide ratio rows

                Swal.fire({
                    toast: true,
                    position: 'top-end',
                    icon: 'success',
                    title: 'ล้างค่าเป้าหมายแล้ว',
                    showConfirmButton: false,
                    timer: 2000
                });
            } else {
                Swal.fire('เกิดข้อผิดพลาด', 'ไม่สามารถล้างค่าเป้าหมายได้', 'error');
            }
        });
    }

    /**
     * NEW: Calculates and displays cumulative periods for ALL units.
     */
    function updateCumulativePeriods() {
        let cumulativePeriods = 0;
        // Iterate through the unit list on the left to maintain correct order
        document.querySelectorAll('#unitList a').forEach(link => {
            const unitId = link.dataset.unitId;
            const periods = unitHoursData[unitId] || 0;
            
            const displaySpan = workspaceTabsContent.querySelector(`#cumulative-display-${unitId}`);
            if (displaySpan) { // อัปเดตเฉพาะ span ที่มองเห็นอยู่
                if (periods > 0) {
                    const startPeriod = cumulativePeriods + 1;
                    const endPeriod = cumulativePeriods + periods;
                    displaySpan.textContent = `(คาบที่ ${startPeriod}-${endPeriod})`;
                    cumulativePeriods = endPeriod;
                } else {
                    displaySpan.textContent = '';
                }
            } else { // สำหรับ unit ที่ไม่ได้แสดงผล ให้บวกค่าไปเฉยๆ
                 if (periods > 0) {
                    cumulativePeriods += periods;
                }
            }
        });
    }

    // --- เพิ่ม Event Listener สำหรับการกรอกชั่วโมง ---
    workspaceTabsContent.addEventListener('input', e => {
        if (e.target.classList.contains('learning-unit-hours-input')) {
            const unitId = e.target.dataset.unitId;
            const periods = parseInt(e.target.value, 10) || 0;
            
            // Update our central data store
            unitHoursData[unitId] = periods;
            
            // Recalculate for all units
            updateCumulativePeriods();
            
            // Debounced save logic (no changes here)
            clearTimeout(hourSaveDebounce);
            hourSaveDebounce = setTimeout(() => {
                fetch(`/teacher/api/units/${unitId}/hours`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ hours: periods })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        Swal.fire({ toast: true, position: 'top-end', icon: 'success', title: 'บันทึกคาบเรียนแล้ว', showConfirmButton: false, timer: 1500 });
                    } else {
                        Swal.fire('เกิดข้อผิดพลาด', data.message, 'error');
                    }
                });
            }, 200);
        }
    });

    /**
     * [SIMPLIFIED] Attaches all necessary event listeners to the gradebook table.
     * The complex calculation logic is now handled by updateStudentRowTotals.
     */
    function setupGradebookEventListeners(table, data) {
        // --- 1. ประกาศตัวแปรที่ใช้ร่วมกัน ---
        let saveDebounce;
        let isDistributing = false;

        // --- 2. สร้างฟังก์ชันย่อย (Helper Functions) ทั้งหมดไว้ข้างใน ---

        /**
         * ฟังก์ชันสำหรับส่งข้อมูลคะแนน 1 รายการไปบันทึกที่ Server
         */
        const saveScore = (inputElement) => {
            // 1. ตรวจสอบ Element เบื้องต้น
            if (!inputElement) {
                console.error("saveScore was called with a null element.");
                return;
            }            
            const studentRow = inputElement.closest('tr');
            if (!studentRow) {
                console.error("Could not find parent <tr> for element:", inputElement);
                return;
            }
            // 2. รวบรวมข้อมูลพื้นฐาน
            const studentId = studentRow.dataset.studentId;
            const courseId = table.dataset.courseId;
            const rawValue = inputElement.value;
            
            let scoreValue = (rawValue === '') ? null : (inputElement.tagName === 'SELECT' ? rawValue : parseFloat(rawValue));
            let apiUrl = '';
            let payload = {};

            // 3. สร้าง Payload ตามประเภทของ Input พร้อมการตรวจสอบ
            if (inputElement.classList.contains('score-input')) {
                const itemId = inputElement.dataset.itemId;
                if (!itemId) {
                    console.error("Missing data-item-id for score input:", inputElement);
                    return;
                }                
                apiUrl = '/teacher/api/scores/save';
                payload = { student_id: studentId, graded_item_id: itemId, score: scoreValue };
            } else if (inputElement.classList.contains('exam-input')) {
                const examType = inputElement.dataset.examType;
                if (!examType) {
                    console.error("Missing data-exam-type for exam input:", inputElement);
                    return;
                }
                apiUrl = '/teacher/api/enrollments/save-exam-score';
                payload = { student_id: studentId, course_id: courseId, exam_type: examType, score: scoreValue };
            } else if (inputElement.matches('.qualitative-select, .qualitative-main-summary')) {
                const topicId = inputElement.dataset.topicId;
                // **นี่คือจุดตรวจสอบที่สำคัญที่สุด**
                if (!topicId) {
                    console.error("Missing data-topic-id for qualitative select:", inputElement);
                    return; // ไม่ส่ง Request ถ้าไม่มี topicId
                }                
                apiUrl = '/teacher/api/qualitative-scores/save';
                payload = { student_id: studentId, course_id: courseId, topic_id: topicId, score: scoreValue };
            }

            // 4. ตรวจสอบข้อมูลทั้งหมดอีกครั้งก่อนส่ง
            if (!apiUrl || !studentId || !courseId) {
                console.error("Cannot save score, required data is missing.", { apiUrl, studentId, courseId });
                return;
            }
            
            // 5. ส่ง Request (Fetch API)
            // console.log("Saving Score:", JSON.stringify(payload)); // (เปิดใช้บรรทัดนี้เพื่อดูข้อมูลที่ส่ง)
            fetch(apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify(payload)
            })
            .then(res => {
                if (!res.ok) {
                    // ถ้า Server ตอบกลับมาเป็น lỗi (เช่น 400, 500) ให้แสดงใน Console
                    console.error(`Error saving score. Status: ${res.status}`, res);
                    return res.json().then(errData => Promise.reject(errData));
                }
                return res.json();
            })
            .then(result => {
                if (result.status === 'success' && result.updated_alerts) {
                    const alertContainer = studentRow.querySelector('.student-alerts-container');
                    if (alertContainer) alertContainer.innerHTML = renderAlerts(result.updated_alerts);
                }
                updateStudentRowTotals(studentRow);
            })
            .catch(err => {
                console.error('Save score failed:', err.message || err);
                updateStudentRowTotals(studentRow); // ยังคงอัปเดต UI แม้จะ Save ไม่สำเร็จ
            });
        };

        /**
         * ฟังก์ชันใหม่สำหรับ Bulk Save (ไม่มีการเปลี่ยนแปลง)
         */
        const saveScoresBulk = (scoresData) => {
            const courseId = table.dataset.courseId;
            fetch('/teacher/api/scores/save-bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ scores: scoresData, course_id: courseId })
            })
            .then(res => res.json())
            .then(result => {
                if (result.status === 'success' && result.updated_alerts_map) {
                    // วนลูปอัปเดต alert และคำนวณเกรดของทุกคนที่ได้รับผลกระทบ
                    for (const studentId in result.updated_alerts_map) {
                        const studentRow = table.querySelector(`tr[data-student-id="${studentId}"]`);
                        if(studentRow){
                            const alertContainer = studentRow.querySelector('.student-alerts-container');
                            if(alertContainer) {
                                alertContainer.innerHTML = renderAlerts(result.updated_alerts_map[studentId]);
                            }
                            updateStudentRowTotals(studentRow);
                        }
                    }
                }
            })
            .catch(err => console.error('Bulk save error:', err));
        };

        const saveQualitativeScoresBulk = (scoresData) => {
            const courseId = table.dataset.courseId;
            fetch('/teacher/api/qualitative-scores/save-bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ scores: scoresData, course_id: courseId })
            })
            .then(res => res.ok ? res.json() : Promise.reject(res))
            .then(result => {
                if (result.status !== 'success') console.error('Qualitative bulk save failed:', result.message);
                // ไม่ต้องทำอะไรต่อ เพราะไม่มี Alert หรือการคำนวณที่ซับซ้อน
            })
            .catch(err => console.error('Qualitative bulk save error:', err));
        };

        const saveExamScoresBulk = (scoresData) => {
            const courseId = table.dataset.courseId;
            fetch('/teacher/api/enrollments/save-exam-score-bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ scores: scoresData, course_id: courseId })
            })
            .then(res => res.ok ? res.json() : Promise.reject(res))
            .then(result => {
                if (result.status !== 'success') console.error('Exam bulk save failed:', result.message);
                // ไม่ต้องทำอะไรต่อ เพราะคะแนนสอบไม่มี Alert
            })
            .catch(err => console.error('Exam bulk save error:', err));
        };

        // --- 3. Main Event Listeners (ที่จัดระเบียบใหม่) ---
        /**
         * ฟังก์ชันย่อยที่ 1: กระจายค่าจาก "หัวข้อใหญ่" ไปยัง "หัวข้อย่อย"
         * @param {HTMLElement} mainSelect - Dropdown ของหัวข้อใหญ่ที่ถูกเปลี่ยน
         * @param {string} scope - ขอบเขตการทำงาน ('table' หรือ 'row')
         * @returns {Array} - รายการ elements ทั้งหมดที่มีการเปลี่ยนแปลง
         */
        const propagateMainToSubs = (mainSelect, scope) => {
            const mainId = mainSelect.dataset.topicId;
            const newValue = mainSelect.value;
            const changes = [mainSelect];
            const rows = (scope === 'table') ? Array.from(table.querySelectorAll('tr[data-student-id]')) : [mainSelect.closest('tr')];

            rows.forEach(row => {
                // อัปเดต Dropdown "สรุป" ของแถวนี้ (กรณี scope='table')
                const summaryInRow = row.querySelector(`.qualitative-main-summary[data-topic-id="${mainId}"]`);
                if (summaryInRow && summaryInRow.value !== newValue) {
                    summaryInRow.value = newValue;
                    changes.push(summaryInRow);
                }
                
                // อัปเดต Dropdown "ย่อย" ทั้งหมดที่เกี่ยวข้อง
                row.querySelectorAll(`.qualitative-select[data-main-id="${mainId}"]`).forEach(sub => {
                    if (sub.value !== newValue) {
                        sub.value = newValue;
                        changes.push(sub);
                    }
                });
            });
            return [...new Set(changes)]; // คืนค่าแบบไม่ซ้ำ
        };
        /**
         * ฟังก์ชันย่อยที่ 2: คำนวณ "หัวข้อใหญ่" ใหม่จาก "หัวข้อย่อย"
         * @param {HTMLElement} subSelect - Dropdown ของหัวข้อย่อยที่ถูกเปลี่ยน
         * @param {string} scope - ขอบเขตการทำงาน ('table' หรือ 'row')
         * @returns {Array} - รายการ elements ทั้งหมดที่มีการเปลี่ยนแปลง
         */
        const recalculateMainFromSubs = (subSelect, scope) => {
            const mainId = subSelect.dataset.mainId;
            const changes = [subSelect];
            const rows = (scope === 'table') ? Array.from(table.querySelectorAll('tr[data-student-id]')) : [subSelect.closest('tr')];

            // ถ้าเป็นโหมด "ทั้งหมด" ให้กระจายค่าของ "หัวข้อย่อย" ไปทุกแถวก่อน
            if (scope === 'table') {
                const topicId = subSelect.dataset.topicId;
                const newValue = subSelect.value;
                rows.forEach(row => {
                    const otherSub = row.querySelector(`.qualitative-select[data-topic-id="${topicId}"]`);
                    if (otherSub && otherSub !== subSelect && otherSub.value !== newValue) {
                        otherSub.value = newValue;
                        changes.push(otherSub);
                    }
                });
            }

            // จากนั้น คำนวณ "สรุป" ใหม่สำหรับทุกแถวใน scope
            rows.forEach(row => {
                const summary = row.querySelector(`.qualitative-main-summary[data-topic-id="${mainId}"]`);
                const subs = Array.from(row.querySelectorAll(`.qualitative-select[data-main-id="${mainId}"]`));
                const scores = subs.map(s => s.value).filter(v => v !== '');

                if (summary && scores.length > 0) {
                    const frequency = scores.reduce((acc, val) => { acc[val] = (acc[val] || 0) + 1; return acc; }, {});
                    const mode = Object.keys(frequency).reduce((a, b) => frequency[a] > frequency[b] ? a : b);
                    if (summary.value !== mode) {
                        summary.value = mode;
                        changes.push(summary);
                    }
                } else if (summary && summary.value !== '') {
                    summary.value = '';
                    changes.push(summary);
                }
            });
            return [...new Set(changes)]; // คืนค่าแบบไม่ซ้ำ
        };

        // Listener สำหรับการ "กรอกข้อมูล" (สำหรับช่องตัวเลข)
        table.addEventListener('input', e => {
            if (isDistributing) return;
            const input = e.target;
            const studentRow = input.closest('tr');
            if (!studentRow) return;
            
            if (input.matches('.score-input, .exam-input')) {
                handlePropagation(input); // เรียกใช้ฟังก์ชันกระจายคะแนน
                updateStudentRowTotals(studentRow);
            }
        });
        
        // Listener สำหรับการ "เปลี่ยนค่า" (สำหรับ Dropdown และ สวิตช์)
        table.addEventListener('change', e => {
            if (isDistributing) return;
            const target = e.target;

            // A. จัดการสวิตช์ (Toggle) - ทำให้เลือกได้เพียงอันเดียว
            if (target.classList.contains('propagation-toggle')) {
                const itemId = target.dataset.itemId;
                const mode = target.dataset.mode;
                const otherToggle = (mode === 'group')
                    ? table.querySelector(`.propagation-toggle.all-toggle[data-item-id="${itemId}"]`)
                    : table.querySelector(`.propagation-toggle.group-toggle[data-item-id="${itemId}"]`);

                if (target.checked && otherToggle) { otherToggle.checked = false; }
                return; 
            }

            // B. จัดการ Dropdown ประเมินผล (Qualitative) - เรียกใช้ฟังก์ชันหลัก
            if (target.matches('.qualitative-select, .qualitative-main-summary')) {
                handleQualitativeChange(target);
            }
        });

        // --- 3. ฟังก์ชันหลักที่ควบคุม Logic การทำงาน ---

        /**
         * ฟังก์ชันใหม่: จัดการการเปลี่ยนแปลงของ Qualitative Dropdown ทั้งหมด
         */
        const handleQualitativeChange = (changedSelect) => {
            isDistributing = true;

            const studentRow = changedSelect.closest('tr');
            if (!studentRow) { isDistributing = false; return; }

            const mainId = changedSelect.dataset.mainId || changedSelect.dataset.topicId;
            const newValue = changedSelect.value;
            const isMainSummary = changedSelect.classList.contains('qualitative-main-summary');
            let allModifiedSelects = [changedSelect];

            // 1. Determine Scope (Row, Group, or All)
            const allToggle = table.querySelector(`.propagation-toggle.all-toggle[data-item-id="${mainId}"]`);
            const groupToggle = table.querySelector(`.propagation-toggle.group-toggle[data-item-id="${mainId}"]`);

            let targetRows = [studentRow]; // Default scope is the current row

            if (allToggle && allToggle.checked) {
                targetRows = Array.from(table.querySelectorAll('tr[data-student-id]'));
            } else if (groupToggle && groupToggle.checked) {
                const groupIds = JSON.parse(studentRow.dataset.groupIds || '{}');
                const unitId = activeUnitId; 
                const targetGroupId = groupIds[unitId];
                if (targetGroupId) {
                    targetRows = Array.from(table.querySelectorAll(`tr[data-group-ids*='"${unitId}":${targetGroupId}']`));
                }
            }

            // 2. Propagate values based on what was changed
            if (isMainSummary) {
                // User changed the MAIN summary: Override all sub-topics in scope
                targetRows.forEach(row => {
                    row.querySelectorAll(`.qualitative-select[data-main-id="${mainId}"]`).forEach(sub => {
                        if (sub.value !== newValue) {
                            sub.value = newValue;
                            allModifiedSelects.push(sub);
                        }
                    });
                    // Also update other main summaries if scope is group/all
                    if (row !== studentRow) {
                        const mainInRow = row.querySelector(`.qualitative-main-summary[data-topic-id="${mainId}"]`);
                        if(mainInRow && mainInRow.value !== newValue) {
                            mainInRow.value = newValue;
                            allModifiedSelects.push(mainInRow);
                        }
                    }
                });
            } else {
                // User changed a SUB-topic: Propagate to the same sub-topic in scope
                const topicId = changedSelect.dataset.topicId;
                targetRows.forEach(row => {
                    if (row !== studentRow) {
                        const subInRow = row.querySelector(`.qualitative-select[data-topic-id="${topicId}"]`);
                        if(subInRow && subInRow.value !== newValue){
                            subInRow.value = newValue;
                            allModifiedSelects.push(subInRow);
                        }
                    }
                });
            }

            // 3. Recalculate Main Summary (Mode) for all affected rows
            targetRows.forEach(row => {
                const mainSummaryInRow = row.querySelector(`.qualitative-main-summary[data-topic-id="${mainId}"]`);
                const subSelectsInRow = Array.from(row.querySelectorAll(`.qualitative-select[data-main-id="${mainId}"]`));

                if (mainSummaryInRow && subSelectsInRow.length > 0) {
                    const subValues = subSelectsInRow.map(s => s.value);
                    const newMode = calculateMode(subValues);
                    if (mainSummaryInRow.value !== newMode) {
                        mainSummaryInRow.value = newMode;
                        allModifiedSelects.push(mainSummaryInRow);
                    }
                }
            });

            // 4. Save all changes with debounce
            if (allModifiedSelects.length > 0) {
                clearTimeout(saveDebounce);
                saveDebounce = setTimeout(() => {
                    const uniqueChanges = [...new Set(allModifiedSelects)];
                    const scoresToSave = uniqueChanges.map(sel => ({
                        student_id: sel.closest('tr')?.dataset.studentId,
                        topic_id: sel.dataset.topicId,
                        score: sel.value === '' ? null : sel.value
                    })).filter(s => s.student_id && s.topic_id);

                    if (scoresToSave.length > 0) {
                        saveQualitativeScoresBulk(scoresToSave);
                    }
                }, 800); // Increased debounce for complex operations
            }

            isDistributing = false;
        };
        
        /**
         * ฟังก์ชันสำหรับจัดการการกระจายคะแนนตัวเลข (Numeric)
         */
        const handlePropagation = (input) => {
            const studentRow = input.closest('tr');
            if (!studentRow) return;
            const itemId = input.dataset.itemId || input.dataset.examType;
            if (!itemId) return;

            const groupToggle = table.querySelector(`.propagation-toggle.group-toggle[data-item-id="${itemId}"]`);
            const allToggle = table.querySelector(`.propagation-toggle.all-toggle[data-item-id="${itemId}"]`);
            const newScore = input.value;
            let inputsToUpdate = [];

            if (allToggle && allToggle.checked) {
                const selector = `.score-input[data-item-id="${itemId}"], .exam-input[data-exam-type="${itemId}"]`;
                inputsToUpdate = Array.from(table.querySelectorAll(selector));
            } else if (groupToggle && groupToggle.checked) {
                const groupIds = JSON.parse(studentRow.dataset.groupIds || '{}');
                const unitId = activeUnitId;
                const targetGroupId = groupIds[unitId];
                if (targetGroupId) {
                    const rowsInGroup = table.querySelectorAll(`tr[data-group-ids*='"${unitId}":${targetGroupId}']`);
                    rowsInGroup.forEach(row => {
                        const selector = `.score-input[data-item-id="${itemId}"], .exam-input[data-exam-type="${itemId}"]`;
                        const inputInRow = row.querySelector(selector);
                        if (inputInRow) inputsToUpdate.push(inputInRow);
                    });
                }
            }

            if (inputsToUpdate.length > 0) {
                isDistributing = true;
                inputsToUpdate.forEach(i => { if (i !== input) i.value = newScore; });
                isDistributing = false;

                clearTimeout(saveDebounce);
                saveDebounce = setTimeout(() => {
                    const firstInput = inputsToUpdate[0];
                    if (firstInput.classList.contains('score-input')) {
                        const scoresToSave = inputsToUpdate.map(i => ({ student_id: i.closest('tr').dataset.studentId, graded_item_id: i.dataset.itemId, score: i.value === '' ? null : parseFloat(i.value) }));
                        if (scoresToSave.length > 0) saveScoresBulk(scoresToSave);
                    } else if (firstInput.classList.contains('exam-input')) {
                        const scoresToSave = inputsToUpdate.map(i => ({ student_id: i.closest('tr').dataset.studentId, exam_type: i.dataset.examType, score: i.value === '' ? null : parseFloat(i.value) }));
                        if (scoresToSave.length > 0) saveExamScoresBulk(scoresToSave);
                    }
                    inputsToUpdate.forEach(i => updateStudentRowTotals(i.closest('tr')));
                }, 500);
            } else {
                clearTimeout(saveDebounce);
                saveDebounce = setTimeout(() => {
                    saveScore(input);
                }, 500);
            }
        };
    }

    // --- UI UPDATE & CALCULATION FUNCTIONS ---

    async function loadRatioTarget() {
        try {
            const resp = await fetch(`/teacher/api/plan/${planId}/ratio-target`);
            if (resp.ok) {
                const data = await resp.json();
                if (data && data.mid_ratio != null && data.final_ratio != null) {
                    targetMidRatio = parseInt(data.mid_ratio);
                    targetFinalRatio = parseInt(data.final_ratio);
                    isTargetSetByUser = true;
                    document.querySelector('#ratioTargetModal #target-mid-ratio').value = targetMidRatio;
                    document.querySelector('#ratioTargetModal #target-final-ratio').value = targetFinalRatio;
                } else {
                    isTargetSetByUser = false;
                }
            }
        } catch (err) {
            console.warn('Could not load ratio target', err);
            isTargetSetByUser = false;
        }
    }

    /**
     * [FINAL VERSION 2.0] Calculates and updates the "Intelligent Score Summary Panel".
     * - Correctly defines Mid-Period vs Final-Period scores.
     * - Changes the "Difference" calculation to show "points needed to reach the 80:20 target".
     * - Uses clearer colors for the difference display (Warning/Danger).
     */
    function updateSummaryPanel() {
        const container = document.getElementById('assessment-content');
        if (!container) return;

        // --- Part 1: Calculate scores using the CORRECT definitions ---
        const totalCollectedScore = Array.from(container.querySelectorAll('.score-value')).reduce((sum, el) => sum + (parseFloat(el.textContent) || 0), 0);
        const totalMidtermScore = Array.from(container.querySelectorAll('.exam-score-input[data-exam-type="midterm"]:not(:disabled)')).reduce((sum, el) => sum + (parseFloat(el.value) || 0), 0);
        const totalFinalScore = Array.from(container.querySelectorAll('.exam-score-input[data-exam-type="final"]:not(:disabled)')).reduce((sum, el) => sum + (parseFloat(el.value) || 0), 0);

        // User's explicit definition of the two buckets
        const actualMidPeriodScore = totalCollectedScore + totalMidtermScore;
        const actualFinalPeriodScore = totalFinalScore;
        const grandTotalScore = actualMidPeriodScore + actualFinalPeriodScore;

        // --- Part 2: Handle UI Visibility ---
        let anyMidtermEnabled = container.querySelector('.exam-score-switch[id^="midterm-"]:checked');
        let anyFinalEnabled = container.querySelector('.exam-score-switch[id^="final-"]:checked');
        
        const midtermRow = document.getElementById('summary-midterm-row');
        const finalRow = document.getElementById('summary-final-row');
        if (midtermRow) midtermRow.style.display = anyMidtermEnabled ? 'block' : 'none';
        if (finalRow) finalRow.style.display = anyFinalEnabled ? 'block' : 'none';
        
        const ratioContainer = document.getElementById('ratio-summary-container');
        if (ratioContainer) {
            ratioContainer.style.display = (anyMidtermEnabled || anyFinalEnabled) ? 'flex' : 'none';
        }

        // --- Part 3: Update Score Displays ---
        document.getElementById('summary-collected-score').textContent = totalCollectedScore;
        document.getElementById('summary-midterm-score').textContent = totalMidtermScore;
        document.getElementById('summary-final-score').textContent = totalFinalScore;
        document.getElementById('summary-total-score').textContent = grandTotalScore;

        // --- Part 4: REVISED Ratio and Difference Calculation ---
        const actualRatioDisplay = document.getElementById('actual-ratio-display');
        const targetRatioCol = document.getElementById('target-ratio-col');
        const diffRatioCol = document.getElementById('diff-ratio-col');
        const targetRatioDisplay = document.getElementById('target-ratio-display');
        const diffRatioDisplay = document.getElementById('diff-ratio-display');

        // Actual Ratio
        if (grandTotalScore > 0) {
            const actualMidRatio = Math.round((actualMidPeriodScore / grandTotalScore) * 100);
            const actualFinalRatio = 100 - actualMidRatio;
            actualRatioDisplay.textContent = `${actualMidRatio} : ${actualFinalRatio}`;
        } else {
            actualRatioDisplay.textContent = '-- : --';
        }

        // Target Ratio and NEW "Points Needed" Logic
        if (isTargetSetByUser) {
            targetRatioCol.style.display = 'block';
            diffRatioCol.style.display = 'block';
            targetRatioDisplay.textContent = `${targetMidRatio} : ${targetFinalRatio}`;
            
            if (actualFinalPeriodScore > 0 && targetFinalRatio > 0) {
                // Calculation for "points needed to reach the target ratio"
                const idealMidPeriodScore = (actualFinalPeriodScore * targetMidRatio) / targetFinalRatio;
                const pointsNeeded = idealMidPeriodScore - actualMidPeriodScore;

                if (pointsNeeded < 0.01 && pointsNeeded > -0.01) {
                    diffRatioDisplay.innerHTML = `<span class="text-success">ตรงตามเป้าหมาย</span>`;
                } else if (pointsNeeded < 0) { // Current score is OVER the target
                    diffRatioDisplay.innerHTML = `<span class="text-danger">ระหว่างภาคเกิน ${Math.abs(pointsNeeded).toFixed(2).replace(/\.00$/, '')} คะแนน</span>`;
                } else { // Current score is UNDER the target
                    diffRatioDisplay.innerHTML = `<span class="text-warning fw-bold">ระหว่างภาคขาด ${pointsNeeded.toFixed(2).replace(/\.00$/, '')} คะแนน</span>`;
                }
            } else {
                diffRatioDisplay.innerHTML = '<span>รอคะแนนปลายภาค</span>';
            }
        } else {
            targetRatioCol.style.display = 'none';
            diffRatioCol.style.display = 'none';
        }
    }

    function buildCheckboxTree(nodes, selectedIds, isSublevel = false) {
        let html = `<ul class="${isSublevel ? 'list-unstyled ps-4' : 'list-unstyled'}">`;
        nodes.forEach(node => {
            const isChecked = selectedIds.includes(node.id);
            html += `<li class="form-check my-1">
                        <input class="form-check-input" type="checkbox" value="${node.id}" id="topic-${node.id}" ${isChecked ? 'checked' : ''}>
                        <label class="form-check-label" for="topic-${node.id}">${node.name}</label>
                        ${node.children?.length > 0 ? buildCheckboxTree(node.children, selectedIds, true) : ''}
                     </li>`;
        });
        return html + '</ul>';
    }

    function setupCheckboxLogic(container) {
        container.addEventListener('change', e => {
            if (e.target.type !== 'checkbox') return;
            const checkbox = e.target;
            const isChecked = checkbox.checked;
            const listItem = checkbox.closest('li.form-check');
            
            // Check/uncheck all children
            listItem.querySelectorAll('input[type="checkbox"]').forEach(child => child.checked = isChecked);

            // Update parents
            let parentLi = listItem.parentElement.closest('li.form-check');
            while (parentLi) {
                const parentCheckbox = parentLi.querySelector('input[type="checkbox"]');
                const siblings = parentLi.querySelectorAll('ul > li > input[type="checkbox"]');
                const anySiblingChecked = Array.from(siblings).some(cb => cb.checked);
                parentCheckbox.checked = anySiblingChecked; // Parent is checked if any child is checked
                parentLi = parentLi.parentElement.closest('li.form-check');
            }
        });
    }

    /**
     * Renders the selected indicators below the Tom-Select input,
     * grouped and sorted by standard and indicator code.
     * @param {object} tomSelectInstance The instance of the Tom-Select component.
     */
    function renderSelectedIndicators(tomSelectInstance) {
        const displayArea = document.getElementById('indicator-display-area');
        if (!displayArea) return;
        displayArea.innerHTML = '';

        // Use tomSelectInstance.options which is the single source of truth
        const selectedItems = tomSelectInstance.items.map(id => tomSelectInstance.options[id]);
        
        // Step 1: Group indicators by their parent standard
        const groupedByStandard = selectedItems.reduce((acc, option) => {
            if (!option || !option.standard_id) return acc;
            const stdId = option.standard_id;
            if (!acc[stdId]) {
                acc[stdId] = {
                    code: option.standard_code,
                    desc: option.standard_desc,
                    indicators: []
                };
            }
            acc[stdId].indicators.push({
                id: option.id,
                code: option.indicator_code,
                desc: option.indicator_desc
            });
            return acc;
        }, {});

        // Step 2: Sort the groups alphabetically by standard code
        const sortedGroupKeys = Object.keys(groupedByStandard).sort((a, b) => {
            return groupedByStandard[a].code.localeCompare(groupedByStandard[b].code);
        });

        // Step 3 & 4: Iterate through sorted groups, sort indicators, and create new HTML
        for (const stdId of sortedGroupKeys) {
            const group = groupedByStandard[stdId];
            const groupDiv = document.createElement('div');
            groupDiv.className = 'indicator-group mt-3';
            
            const header = document.createElement('div');
            header.className = 'h6';
            header.innerHTML = `<i class="bi bi-bookmark-star-fill text-primary"></i> ${group.code} ${group.desc}`;
            groupDiv.appendChild(header);

            const list = document.createElement('ul');
            list.className = 'list-group list-group-flush';

            group.indicators.sort((a, b) => a.code.localeCompare(b.code));

            group.indicators.forEach(indicator => {
                const listItem = document.createElement('li');
                listItem.className = 'list-group-item d-flex justify-content-between align-items-center ps-4';
                
                const textSpan = document.createElement('span');
                textSpan.textContent = `${indicator.code} ${indicator.desc}`;
                listItem.appendChild(textSpan);
                
                const removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.className = 'btn btn-sm btn-outline-danger border-0 flex-shrink-0 ms-2';
                removeBtn.innerHTML = '<i class="bi bi-x-circle"></i>';
                removeBtn.title = 'ลบตัวชี้วัดนี้';
                removeBtn.onclick = () => tomSelectInstance.removeItem(indicator.id);
                
                listItem.appendChild(removeBtn);
                list.appendChild(listItem);
            });

            groupDiv.appendChild(list);
            displayArea.appendChild(groupDiv);
        }
    }
    /**
     * Calculates the mode (most frequent value) from an array of values.
     * @param {Array<string>} arr The array of scores/values.
     * @returns {string} The most frequent value, or an empty string if none.
     */
    function calculateMode(arr) {
        if (!arr || arr.length === 0) return '';
        const frequency = arr.reduce((acc, val) => {
            if (val !== '') { // Only count non-empty values
                acc[val] = (acc[val] || 0) + 1;
            }
            return acc;
        }, {});

        let maxFreq = 0;
        let mode = '';
        for (const val in frequency) {
            if (frequency[val] > maxFreq) {
                maxFreq = frequency[val];
                mode = val;
            }
        }
        return mode;
    }
});
