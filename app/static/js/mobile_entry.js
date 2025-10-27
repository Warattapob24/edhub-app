document.addEventListener('DOMContentLoaded', () => {

    // --- UTILITIES ---------------------------------------------------

    function debounce(func, wait) {
        let timeout;
        return function(...args) {
            const context = this;
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(context, args), wait);
        };
    }

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    async function apiCall(url, method = 'POST', body = {}) {
        try {
            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            };
            if (csrfToken) {
                headers['X-CSRFToken'] = csrfToken;
            }
            const response = await fetch(url, {
                method: method,
                headers: headers,
                body: JSON.stringify(body),
            });
            if (!response.ok) {
                throw new Error(`API call failed: ${response.statusText}`);
            }
            // Handle 200 OK but server-side error
            const result = await response.json();
            if (result.status === 'error') {
                 throw new Error(result.message || 'Server returned an error');
            }
            return result; // Return the JSON result
        } catch (error) {
            console.error('API Error:', error);
            Swal.fire({
                icon: 'error',
                title: 'API Error',
                text: error.message,
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 3000
            });
            return null;
        }
    }


    // --- STATE & ELEMENTS ---------------------------------------------
    
    const container = document.getElementById('mobileEntryContainer');
    const studentGrid = document.getElementById('studentGrid');
    const gradedItemSelect = document.getElementById('gradedItemSelect');
    const groupingModalEl = document.getElementById('groupingModal');
    
    const groupingModal = new bootstrap.Modal(groupingModalEl);
    const randomStudentModal = new bootstrap.Modal(document.getElementById('randomStudentModal'));

    const ENTRY_ID = container.dataset.entryId;
    const COURSE_ID = container.dataset.courseId;
    const DATE_ISO = container.dataset.dateIso;
    
    // --- START MODIFICATION (Load scores) ---
    // 1. อ่านข้อมูลจาก global variable ที่ปลอดภัย (แทน data-all-scores)
    let ALL_SCORES = {};
    try {
         // Check if the global variable from the <script> tag exists
         if (typeof ALL_SCORES_DATA !== 'undefined') {
            // >>> FIX: Parse the JSON string into an actual JavaScript Object <<<
            ALL_SCORES = JSON.parse(ALL_SCORES_DATA); 
         } else {
            console.error("ALL_SCORES_DATA is not defined. Check template.");
         }
    } catch (e) {
        // Catch errors during JSON.parse()
        console.error("Could not parse score data:", e); 
        ALL_SCORES = {};
    }

    let studentData = [];
    let sortableInstances = {};


    // --- ATTENDANCE (Drag & Drop) ------------------------------------

    function initializeAttendanceDragDrop() {
        new Sortable(studentGrid, {
            group: 'students',
            animation: 150,
            ghostClass: 'dragging',
            onEnd: (evt) => {}
        });

        document.querySelectorAll('.status-zone').forEach(zone => {
            new Sortable(zone, {
                group: 'students',
                animation: 150,
                onAdd: (evt) => {
                    const draggedItem = evt.item; 
                    const card = draggedItem.querySelector('.student-card'); 
                    if (!card) return;
                    const studentId = card.dataset.studentId;
                    const status = zone.dataset.status;
                    card.dataset.status = status;
                    saveAttendance(studentId, status);
                    studentGrid.appendChild(draggedItem);
                }
            });
        });
    }

    const saveAttendance = debounce(async (studentId, status) => {
        console.log(`Saving attendance: Student ${studentId}, Status ${status}, Entry ${ENTRY_ID}, Date ${DATE_ISO}`);
        const payload = {
            student_id: studentId,
            entry_id: ENTRY_ID,
            date: DATE_ISO,
            status: status
        };
        await apiCall('/teacher/api/attendance/save', 'POST', payload);
    }, 800);


    // --- SCORING (SweetAlert Function) --------------------------------

    async function promptForScore(card, studentId, studentName) {
        const gradedItemId = gradedItemSelect.value;
        const gradedItemText = gradedItemSelect.options[gradedItemSelect.selectedIndex].text;

        if (!gradedItemId) {
            Swal.fire(
                'ยังไม่เลือกรายการ',
                'กรุณาเลือก "รายการให้คะแนน" ที่หัวข้อด้านบนก่อนครับ',
                'warning'
            );
            return;
        }

        const scoreDisplay = card.querySelector('.score-display');
        const currentScore = scoreDisplay.textContent.trim();
        
        const { value: newScore, isConfirmed } = await Swal.fire({
            title: `ให้คะแนน: ${studentName}`,
            text: `รายการ: ${gradedItemText}`,
            input: 'number',
            inputValue: currentScore === '-' ? '' : currentScore,
            inputAttributes: {
                step: '0.25'
            },
            showCancelButton: true,
            confirmButtonText: 'บันทึกคะแนน',
            cancelButtonText: 'ยกเลิก',
            // This makes sure the SweetAlert appears above the (hidden) modal
            customClass: {
                popup: 'swal-on-top' 
            }
        });

        if (isConfirmed && newScore !== null && newScore.trim() !== '') {
            const scoreValue = parseFloat(newScore);
            if (isNaN(scoreValue)) {
                 Swal.fire('ผิดพลาด', 'กรุณากรอกคะแนนเป็นตัวเลข', 'error');
                 return;
            }
            scoreDisplay.textContent = scoreValue;
            saveScore(studentId, gradedItemId, scoreValue, scoreDisplay);
        }
    }

    function initializeScoring() {
        studentGrid.addEventListener('dblclick', (e) => {
            const card = e.target.closest('.student-card');
            if (!card) return;
            const studentId = card.dataset.studentId;
            const studentName = card.querySelector('.student-name').textContent.trim();
            promptForScore(card, studentId, studentName);
        });
    }

    const saveScore = debounce(async (studentId, gradedItemId, score, displayElement) => {
        console.log(`Saving score: Student ${studentId}, Item ${gradedItemId}, Score ${score}`);

        const payload = {
            scores: [{
                student_id: parseInt(studentId, 10),
                graded_item_id: parseInt(gradedItemId, 10),
                score: parseFloat(score)
            }],
            course_id: parseInt(COURSE_ID, 10) 
        };
        console.log("Payload being sent:", JSON.stringify(payload));
        const result = await apiCall('/teacher/api/scores/save-bulk', 'POST', payload);
        
        if (result && result.status === 'success') { // Check server success status
            displayElement.style.color = '#198754'; // Green
            setTimeout(() => { displayElement.style.color = '#0d6efd'; }, 1000); // Revert

            // --- START MODIFICATION (Update local score map) ---
            // 2. Update the local ALL_SCORES map
            if (!ALL_SCORES[studentId]) {
                ALL_SCORES[studentId] = {};
            }
            ALL_SCORES[studentId][gradedItemId] = score;
            // --- END MODIFICATION ---

        } else {
            displayElement.style.color = '#dc3545'; // Red
            // Revert text if save failed
            displayElement.textContent = ALL_SCORES[studentId]?.[gradedItemId] || '-';
        }

    }, 800);

    /**
     * 3. This new function updates all score displays when the dropdown changes.
     */
    function updateScoreDisplays(selectedItemId) {
        console.log(`Dropdown changed. Selected Item ID: '${selectedItemId}'`);

        if (!selectedItemId) {
            document.querySelectorAll('.score-display').forEach(display => display.textContent = '-');
            return;
        }

        // Ensure keys are strings for lookup
        const itemIdStr = String(selectedItemId);

        // Log the entire map ONCE when the dropdown changes (uses a simple flag)
        if (!window.loggedScoreMap) {
             console.log("ALL_SCORES map:", JSON.stringify(ALL_SCORES)); // Log as JSON string for clarity
             window.loggedScoreMap = true;
        }

        document.querySelectorAll('.student-card').forEach(card => {
            const studentIdStr = card.dataset.studentId; // String
            const display = card.querySelector('.score-display');

            let score = undefined; // Default to undefined

            // More explicit check: Does the student key exist?
            if (ALL_SCORES.hasOwnProperty(studentIdStr)) {
                const studentScores = ALL_SCORES[studentIdStr];
                // Does the item key exist for this student?
                if (studentScores.hasOwnProperty(itemIdStr)) {
                    score = studentScores[itemIdStr];
                }
            }

            // Log result for EACH student
            console.log(` -> Student '${studentIdStr}', Item '${itemIdStr}': Score found = ${score}`);

            if (score !== undefined && score !== null) {
                display.textContent = Number(score.toFixed(2));
            } else {
                display.textContent = '-';
            }
        });
    }

    // --- GROUPING (Drag & Drop in Modal) -----------------------------

    function initializeGroupingDragDrop() {
        sortableInstances['null'] = new Sortable(ungroupedStudentsArea, {
            group: 'grouping',
            animation: 150,
            ghostClass: 'dragging',
            onAdd: (evt) => handleGroupDrop(evt, null)
        });

        document.querySelectorAll('#groupZonesContainer .group-zone').forEach(zone => {
            const groupId = zone.dataset.groupId;
            sortableInstances[groupId] = new Sortable(zone, {
                group: 'grouping',
                animation: 150,
                ghostClass: 'dragging',
                onAdd: (evt) => handleGroupDrop(evt, groupId)
            });
        });
    }

    function handleGroupDrop(event, newGroupId) {
        const card = event.item;
        const enrollmentId = card.dataset.enrollmentId;
        console.log(`Assigning group: Enrollment ${enrollmentId} to Group ${newGroupId}`);
        apiCall('/teacher/api/enrollments/assign-group', 'POST', {
            enrollment_ids: [enrollmentId],
            group_id: newGroupId === 'null' ? null : newGroupId
        });
    }

    function populateGroupingModal() {
        ungroupedStudentsArea.innerHTML = '';
        document.querySelectorAll('#groupZonesContainer .group-zone').forEach(zone => {
            zone.innerHTML = '';
        });
        const allEnrollments = Array.from(document.querySelectorAll('#studentGrid .student-card'));
        allEnrollments.forEach(mainCard => {
            const modalCard = document.createElement('div');
            modalCard.className = 'student-card';
            modalCard.dataset.enrollmentId = mainCard.dataset.enrollmentId;
            modalCard.innerHTML = `
                <span class="student-number">${mainCard.querySelector('.student-number').textContent}</span>
                <div class="student-name">${mainCard.querySelector('.student-name').textContent}</div>
            `;
            ungroupedStudentsArea.appendChild(modalCard);
        });
    }

    createGroupBtn.addEventListener('click', async () => {
        const groupName = prompt('กรุณาตั้งชื่อกลุ่มใหม่:');
        if (!groupName || groupName.trim() === '') return;
        const result = await apiCall('/teacher/api/student-groups', 'POST', {
            name: groupName,
            course_id: COURSE_ID
        });
        if (result && result.id) {
            const newGroupContainer = document.createElement('div');
            newGroupContainer.className = 'group-container mb-3';
            newGroupContainer.id = `group-container-${result.id}`;
            newGroupContainer.innerHTML = `
                <h6><i class="bi bi-collection-fill"></i> ${result.name}</h6>
                <div class="group-zone drop-zone" data-group-id="${result.id}"></div>
            `;
            groupZonesContainer.appendChild(newGroupContainer);
            const newZone = newGroupContainer.querySelector('.group-zone');
            sortableInstances[result.id] = new Sortable(newZone, {
                group: 'grouping',
                animation: 150,
                ghostClass: 'dragging',
                onAdd: (evt) => handleGroupDrop(evt, result.id)
            });
        }
    });

    groupingModalEl.addEventListener('show.bs.modal', () => {
        populateGroupingModal();
    });


    // --- RANDOM STUDENT (Modal) --------------------------------------

    function initializeRandomStudent() {
        document.querySelectorAll('#studentGrid .student-card').forEach(card => {
            studentData.push({
                id: card.dataset.studentId,
                name: card.querySelector('.student-name').textContent.trim()
            });
        });

        document.getElementById('spinWheelBtn').addEventListener('click', () => {
            spinWheel();
        });
    }

    /**
     * MODIFIED: Hides the Random modal before showing the Score modal,
     * then shows it again after the Score modal is closed.
     */
    function spinWheel() {
        if (typeof Winwheel === 'undefined') {
            console.warn('Winwheel.js not loaded. Using simple randomizer.');
            
            if (studentData.length === 0) return;

            const randomIndex = Math.floor(Math.random() * studentData.length);
            const winner = studentData[randomIndex];
            
            const resultEl = document.getElementById('randomResult');
            const placeholderEl = document.getElementById('wheelPlaceholder');
            
            resultEl.textContent = '...';
            resultEl.style.display = 'block';
            resultEl.style.cursor = 'default';
            resultEl.style.textDecoration = 'none';
            resultEl.onclick = null;
            placeholderEl.style.display = 'none';

            setTimeout(() => {
                resultEl.textContent = winner.name;
                resultEl.style.cursor = 'pointer';
                resultEl.style.textDecoration = 'underline';

                const card = highlightStudentCard(winner.id);
                
                // --- START MODIFICATION ---
                // Create an ASYNC click listener
                resultEl.onclick = async () => { 
                    if (card) {
                        // 1. Hide the randomizer modal
                        randomStudentModal.hide(); 

                        // 2. Wait for the score prompt to finish
                        await promptForScore(card, winner.id, winner.name); 
                        
                        // 3. Show the randomizer modal again
                        randomStudentModal.show(); 
                    } else {
                        console.error('Could not find card for winner:', winner.id);
                        Swal.fire('Error', 'Could not find student card.', 'error');
                    }
                };
                // --- END MODIFICATION ---

            }, 1000); // Simulate spin time

        } else {
            // TODO: Implement actual Winwheel.js logic
        }
    }

    function highlightStudentCard(studentId) {
        document.querySelectorAll('.student-card.highlight').forEach(card => {
            card.classList.remove('highlight');
        });

        const card = document.querySelector(`.student-card[data-student-id="${studentId}"]`);
        if (card) {
            card.classList.add('highlight');
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            setTimeout(() => {
                card.classList.remove('highlight');
            }, 3000);
            
            return card;
        }
        return null;
    }

    const style = document.createElement('style');
    style.innerHTML = `
        .student-card.highlight {
            transform: scale(1.1);
            box-shadow: 0 0 15px 5px #0d6efd;
            border: 2px solid #0d6efd;
            z-index: 100;
        }
        #randomResult[style*="cursor: pointer"] {
            color: #0d6efd;
            transition: color 0.2s;
        }
        #randomResult[style*="cursor: pointer"]:hover {
            color: #0a58ca;
        }
        /* Fix for SweetAlert on top of Bootstrap Modal */
        .swal-on-top {
            z-index: 1060 !important; /* Higher than Bootstrap's 1055 */
        }
    `;
    document.head.appendChild(style);


    // --- INITIALIZATION ----------------------------------------------
    
    initializeAttendanceDragDrop();
    initializeScoring();
    initializeGroupingDragDrop();
    initializeRandomStudent();
    // 4. Add listener to update scores when dropdown changes
    gradedItemSelect.addEventListener('change', (e) => {
        updateScoreDisplays(e.target.value);
    });
    
    // 5. Call it once on load
    updateScoreDisplays(gradedItemSelect.value);
});