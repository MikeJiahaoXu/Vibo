// ===================== FROM WEBSITE ===================== //

// Function to send events to the backend server
function sendEvent(eventType, additionalInfo = {}) {
    const video = document.querySelector('video');
    const videoId = video ? new URLSearchParams(window.location.search).get('v') : null;
    const timestamp = video ? video.currentTime : 0;  // Current playback time of the video in seconds

    const data = {
        videoId: videoId,
        event: eventType,
        timestamp: timestamp,
        ...additionalInfo  // Include any additional information
    };

    fetch('https://vibo-3137133b97c9.herokuapp.com', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    }).then(response => response.text())
      .then(result => console.log('Server response:', result))
      .catch(error => console.error('Error:', error));
}

function sendCloseEvent() {
    sessionStorage.removeItem('pageLoaded');
    chrome.runtime.sendMessage({ action: 'checkYouTubeTabs' }, function(response) {
        if (response.noYouTubeTabs) {
            sessionStorage.removeItem('chatMessages');
            sessionStorage.removeItem('chatDialogContent');
        }
    });
}

// Check if the current content is an ad
function isAdPlaying() {
    // This selector might need to be updated based on YouTube's current implementation
    return document.querySelectorAll('.ad-showing, .adsbygoogle').length > 0;
}

let lastEventType = null;
let adWasPlaying = false;

// Setup listeners on a video element
function setupVideoListeners(video) {
    video.addEventListener('play', () => {
        if (isAdPlaying()) {
            sendEvent('adPlay');
            adWasPlaying = true;
        } else if (adWasPlaying) {
            adWasPlaying = false;
            setTimeout(() => {
                // Delay sending the play event to ensure the correct timestamp after an ad
                sendEvent('play');
            }, 200);
        } else {
            sendEvent('play');
        }
    });

    video.addEventListener('pause', () => {
        if (!isAdPlaying()) {
            let videoEnded = (video.currentTime >= (video.duration - 0.1)); // Check if within 0.5 seconds of the end
            if (videoEnded) {
                sendEvent('end');
            } else {
                sendEvent('pause');
            }
        }
    });

    // Monitor playback rate changes
    let lastPlaybackRate = video.playbackRate;
    setInterval(() => {
        if (video.playbackRate !== lastPlaybackRate) {
            sendEvent('playbackRateChange', { playbackRate: video.playbackRate });
            lastPlaybackRate = video.playbackRate;
        }
    }, 200); // Check every 0.2 seconds
}

// Check for videos immediately and set up listeners
function checkAndSetupVideos() {
    const videos = document.querySelectorAll('video');
    videos.forEach(video => {
        if (!video.hasAttribute('data-listeners-added')) {
            video.setAttribute('data-listeners-added', 'true');
            setupVideoListeners(video);
            // Ensure play event is sent when video starts playing after navigation or refresh
            if (!video.paused) {
                sendEvent('play');
            }
        }
    });
}

// Use a Mutation Observer to handle dynamically added videos
function setupMutationObserver() {
    const observer = new MutationObserver(mutations => {
        mutations.forEach(mutation => {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType === 1 && (node.tagName === 'VIDEO' || node.querySelector('video'))) {
                    const videoNode = node.tagName === 'VIDEO' ? node : node.querySelector('video');
                    if (videoNode && !videoNode.hasAttribute('data-listeners-added')) {
                        videoNode.setAttribute('data-listeners-added', 'true');
                        setupVideoListeners(videoNode);
                        // Ensure play event is sent when video starts playing after navigation or refresh
                        if (!videoNode.paused) {
                            sendEvent('play');
                        }
                    }
                }
            });
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });
}

let textboxOverlay = null;

// Initial setup
// if (document.readyState === 'loading') {
//     document.addEventListener('DOMContentLoaded', () => {
//         checkAndSetupVideos();
//         setupMutationObserver();
//     });
// } else {
//     checkAndSetupVideos();
//     setupMutationObserver();
// }

// Initial setup
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        ensureHeadAvailable(() => {
            appendStyles();
            ensureBodyAvailable(() => {
                checkAndSetupVideos();
                setupMutationObserver();
                initializeChatUI(); // Ensure chat UI is initialized
                setupEventSource(); // Ensure SSE connection is initialized
                restoreChatDialogContent();
                textboxOverlay = createTextboxOverlay(); // Initialize textbox overlay
            });
        });
    });
} else {
    ensureHeadAvailable(() => {
        appendStyles();
        ensureBodyAvailable(() => {
            checkAndSetupVideos();
            setupMutationObserver();
            initializeChatUI(); // Ensure chat UI is initialized
            setupEventSource(); // Ensure SSE connection is initialized
            restoreChatDialogContent();
            textboxOverlay = createTextboxOverlay(); // Initialize textbox overlay
        });
    });
}



// Handle cases where video plays automatically on page load
setTimeout(() => {
    const video = document.querySelector('video');
    if (video && !video.paused && !video.hasAttribute('data-listeners-added')) {
        // Video is playing automatically
        video.setAttribute('data-listeners-added', 'true');
        setupVideoListeners(video);
        sendEvent(isAdPlaying() ? 'adPlay' : 'play');
    }
}, 1000); // Delay this check to give YouTube time to start the video

document.addEventListener('keydown', function(event) {
    const activeElement = document.activeElement;
    if (activeElement && activeElement.tagName === 'INPUT' && activeElement.classList.contains('chatInput')) {
        // If the focused element is the chat input, prevent arrow keys from affecting the video
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.stopPropagation();
        }
    } else {
        // Normal behavior when not focused on the chat input
        const video = document.querySelector('video');
        if (!video) return;

        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            const skipTime = event.key === 'ArrowLeft' ? -5 : 5;
            const currentTime = video.currentTime;
            const timestamp = currentTime + skipTime;
            video.currentTime = timestamp;

            fetch('https://vibo-3137133b97c9.herokuapp.com', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    videoId: new URLSearchParams(window.location.search).get('v'),
                    event: 'skip',
                    timestamp: timestamp,
                    skipTime: skipTime
                })
            }).then(response => response.text())
            .then(result => console.log('Server response:', result))
            .catch(error => console.error('Error:', error));
        }
    }
});





// ===================== TO WEBSITE ===================== //

let chatDialog; 
let showChatButton; 

function setupEventSource() {
    const eventSource = new EventSource('https://vibo-3137133b97c9.herokuapp.com/events');
    const video = document.querySelector('video');

    let endTime = null;

    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        console.log("Receiving this: " + data)
        
        switch (data.command) {
            case 'pause':
                if (!video) return;
                video.pause();
                playPauseButton.style.display = 'block';
                break;
            case 'play':
                if (!video) return;
                video.play();
                playPauseButton.innerHTML = pauseIcon;
                playPauseButton.style.display = 'none';
                break;
            case 'displayText':
                if (data.text) {
                    displayTextOnVideo(data.text, data.style, data.endless);
                }
                break;
            case 'bot_response':
                if (chatDialog.style.display === 'none') {
                    showChatButton.querySelector('.redDot').style.display = 'block';
                }
                displayBotMessage(data.text);
                break;
            case 'jump':
                if (!video) return;
                video.currentTime = data.time;
                break;
            case 'clear_all_comments':
                clearTextOverlays();
                break;
            case 'navigate':
                if (data.video_id) {
                    endTime = data.end_time || null;
                    const startTime = data.start_time || 0; 
                    window.location.href = `https://www.youtube.com/watch?v=${data.video_id}&t=${startTime}s`;
                }
                break;
            case 'update_customization':
                updateCustomization(data.userInfo, data.chatbotBehavior);
                break;
                
        }
    };

    eventSource.onopen = function() {
        console.log('SSE opened');
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE Error:', error);
        setTimeout(() => {
            setupEventSource(); // attempt to reconnect
        }, 2000);
    };

    function checkEndTime() {
        if (endTime !== null && video.currentTime >= endTime) {
            video.pause();
            sendEndTimeReachedEvent();
            endTime = null; // Reset endTime after it's reached
        }
    }
    
    if (video){
        video.addEventListener('timeupdate', checkEndTime);
    }
}

// Initialize the SSE connection when the document is ready
document.addEventListener('DOMContentLoaded', setupEventSource);

// Function to send end_time_reached event to the backend server
function sendEndTimeReachedEvent() {
    const data = {
        event: 'end_time_reached'
    };

    fetch('https://vibo-3137133b97c9.herokuapp.com', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    }).then(response => response.text())
      .then(result => console.log('Server response:', result))
      .catch(error => console.error('Error:', error));
}



function createTextboxOverlay(style) {
    const overlay = document.createElement('div');
    overlay.className = 'customTextboxOverlay';
    overlay.style.position = 'fixed';
    overlay.style.top = '50px'; 
    overlay.style.left = '50%';
    overlay.style.transform = 'translateX(-50%)';
    overlay.style.zIndex = '1000000';
    overlay.style.color = style ? 'yellow' : 'white';
    overlay.style.fontSize = '22px';
    overlay.style.fontFamily = 'Arial, sans-serif';
    overlay.style.padding = '12px';
    overlay.style.background = style ? 'rgba(0, 0, 0, 0.45)' : 'rgba(0, 0, 0, 0.55)';
    overlay.style.borderRadius = '8px';
    overlay.style.display = 'none';
    overlay.style.whiteSpace = 'pre-wrap';
    overlay.style.maxWidth = '80%';
    overlay.style.width = 'auto';
    overlay.style.boxShadow = style ? '0 4px 8px rgba(0, 0, 0, 0.3)' : 'none';

    const closeButton = document.createElement('span');
    closeButton.textContent = '×';
    closeButton.style.position = 'absolute';
    closeButton.style.top = '-6px';
    closeButton.style.right = '-6px';
    closeButton.style.color = 'rgba(0, 0, 0, 0.75)';
    closeButton.style.cursor = 'pointer';
    closeButton.style.fontSize = '16px';
    closeButton.style.lineHeight = '16px'; 
    closeButton.style.width = '16px'; 
    closeButton.style.height = '16px'; 
    closeButton.style.textAlign = 'center';
    closeButton.style.background = 'rgba(255, 255, 255, 0.85)';
    closeButton.style.borderRadius = '50%';
    closeButton.style.display = 'none';
    closeButton.style.opacity = '0';
    closeButton.style.transition = 'opacity 0.5s';
    closeButton.style.fontWeight = 'bold';
    closeButton.className = 'closeButton';

    closeButton.onclick = function() {
        overlay.style.display = 'none';
        this.style.display = 'none';
        adjustOverlays();
    };

    overlay.appendChild(closeButton);

    document.body.appendChild(overlay);
    return overlay;
}

// Initialize the textbox overlay when the document is fully loaded or immediately if already loaded
// if (document.readyState === 'loading') {
//     document.addEventListener('DOMContentLoaded', () => {
//         let textboxOverlay = null;
//     });
// } else {
//     textboxOverlay = createTextboxOverlay();
// }

function displayTextOnVideo(text, style = false, endless = false) {
    const overlay = createTextboxOverlay(style);  // Reference the pre-created overlay
    const closeButton = overlay.querySelector('.closeButton'); // Attempt to find the close button

    if (!closeButton) {
        console.error('Close button not found!');
        return;
    }

    overlay.textContent = '';
    overlay.appendChild(closeButton); // Re-append the close button to ensure it is correctly positioned after clearing text content
    closeButton.style.display = 'none';  // Ensure it starts hidden each time text is displayed

    // overlay.appendChild(document.createTextNode(text)); // Add text as a text node to preserve other elements like closeButton

    const textNode = document.createElement('span');
    textNode.textContent = text;
    textNode.style.whiteSpace = 'pre-wrap';

    // Create a temporary element to measure text width, then set the overlay width manually
    const tempElement = document.createElement('div');
    tempElement.style.position = 'absolute';
    tempElement.style.visibility = 'hidden';
    tempElement.style.fontSize = '22px';
    tempElement.style.fontFamily = 'Arial, sans-serif';
    tempElement.style.padding = '12px';
    tempElement.style.whiteSpace = 'pre-wrap';
    tempElement.appendChild(textNode);
    document.body.appendChild(tempElement);
    const textWidth = tempElement.offsetWidth - window.innerWidth * 0.01;
    document.body.removeChild(tempElement);
    const maxWidth = window.innerWidth * 0.8
    const overlayWidth = Math.min(textWidth, maxWidth);
    overlay.style.width = `${overlayWidth}px`;

    // Append the text node to the overlay
    overlay.appendChild(textNode);

    overlay.style.display = 'block';

    let displayDuration = endless ? null : 12000;
    let timer;
    if (displayDuration !== null) {
        timer = setTimeout(() => {
            if (overlay.style.display !== 'none') {
                overlay.style.display = 'none';
                closeButton.style.display = 'none';
                adjustOverlays();
            }
        }, displayDuration);
    }

    overlay.onclick = function() {
        clearTimeout(timer);
        overlay.style.cursor = 'default';
        overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
        closeButton.style.display = 'block';
        closeButton.style.opacity = '1';
    };

    adjustOverlays();
}

function adjustOverlays() {
    const overlays = document.querySelectorAll('.customTextboxOverlay');
    let currentTop = 50; 
    overlays.forEach((overlay, index) => {
        if (overlay.style.display !== 'none') {
            overlay.style.top = `${currentTop}px`;
            currentTop += overlay.offsetHeight + 10; 
        }
    });
}



// const playIcon = `<svg viewBox="0 0 24 24" width="24" height="24" fill="white"><path d="M8 5v14l11-7z"></path></svg>`;
// const pauseIcon = `<svg viewBox="0 0 24 24" width="24" height="24" fill="white"><path d="M6 6h5v12H6zm7 0h5v12h-5z"></path></svg>`;

// let playPauseButton;

// document.addEventListener('DOMContentLoaded', function() {
//     playPauseButton = createPlayPauseButton();  // Initialize button
//     setupEventSource(); 
// });

// function createPlayPauseButton() {
//     const button = document.createElement('button');
//     button.className = 'playPauseButton';
//     button.innerHTML = pauseIcon; 
//     button.style.position = 'fixed';
//     button.style.bottom = '100px';
//     button.style.right = '40px';
//     button.style.fontSize = '35px';
//     button.style.color = 'white';
//     button.style.background = 'rgba(0, 0, 0, 0.75)';
//     button.style.border = 'none';
//     button.style.borderRadius = '50%';
//     button.style.width = '50px';
//     button.style.height = '50px';
//     button.style.padding = '0';  
//     button.style.lineHeight = '50px'; 
//     button.style.textAlign = 'center';
//     button.style.display = 'none';
//     button.style.cursor = 'pointer';
//     button.style.zIndex = '1000001';
//     button.style.alignItems = 'center';
//     button.style.justifyContent = 'center'; 

//     button.onclick = function() {
//         if (button.innerHTML === pauseIcon) {
//             button.innerHTML = playIcon;
//             sendEvent('comment_pause');
//         } else {
//             button.innerHTML = pauseIcon;
//             sendEvent('comment_replay');
//         }
//     };

//     document.body.appendChild(button);
//     return button;
// }



// Delay the execution of the script setup to ensure YouTube scripts have loaded
setTimeout(() => {
    setupYouTubeEventListeners();
}, 3000); // Adjust delay as necessary

function setupYouTubeEventListeners() {
    window.addEventListener('yt-navigate-finish', function() {
        clearTextOverlays();
    });
}

function clearTextOverlays() {
    const overlays = document.querySelectorAll('.customTextboxOverlay');
    overlays.forEach(overlay => {
        overlay.style.display = 'none';
    });
}


function ensureHeadAvailable(callback) {
    if (document.head) {
        callback();
    } else {
        setTimeout(() => ensureHeadAvailable(callback), 100); // Retry after 100ms
    }
}

function ensureBodyAvailable(callback) {
    if (document.body) {
        callback();
    } else {
        setTimeout(() => ensureBodyAvailable(callback), 100); // Retry after 100ms
    }
}

function appendStyles() {
    const style = document.createElement('style');
    style.innerHTML = `
        .chatDialog {
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 30%;
            height: 66%;
            background: rgba(0, 0, 0, 0.5);
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            z-index: 1000002;
            overflow: hidden;
        }

        .resizable {
            position: absolute;
            z-index: 1000003;
        }
        
        .resizable-top {
            top: -4px;
            left: 0;
            right: 0;
            height: 8px;
            cursor: n-resize;
        }

        .resizable-right {
            top: 0;
            right: -4px;
            bottom: 0;
            width: 8px;
            cursor: e-resize;
        }

        .resizable-bottom {
            left: 0;
            right: 0;
            bottom: -4px;
            height: 8px;
            cursor: s-resize;
        }

        .resizable-left {
            top: 0;
            left: -4px;
            bottom: 0;
            width: 8px;
            cursor: w-resize;
        }

        .chatHeader {
            background: rgba(0, 0, 0, 0.65);
            padding: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: move;
        }

        .chatTitle {
            font-size: 16px;
            color: white;
            user-select: none;
        }

        .closeChat {
            font-size: 16px;
            color: white;
            cursor: pointer;
            user-select: none;
        }

        .chatContent {
            flex: 1;
            padding: 10px;
            overflow-y: auto;
        }

        .chatFooter {
            background: rgba(0, 0, 0, 0.65);
            padding: 10px;
            display: flex;
        }

        .chatInput {
            flex: 1;
            padding: 10px;
            border: none;
            border-radius: 4px;
            resize: none;
        }

        .sendChat {
            margin-left: 10px;
            padding: 10px 20px;
            background: rgba(0, 0, 0, 0.65);
            border: none;
            border-radius: 4px;
            cursor: pointer;
            color: white;
        }

        .userMessage {
            text-align: left;
            background: rgba(0, 0, 0, 0.65);
            margin: 5px 0;
            padding: 10px;
            border-radius: 4px;
            color: white;
            display: inline-block;
            max-width: 80%;
            font-size: 18px;
            word-wrap: break-word;
        }

        .userMessageContainer {
            text-align: right;
        }

        .botMessage {
            text-align: left;
            background: rgba(0, 0, 0, 0.4);
            margin: 5px 0;
            padding: 10px;
            border-radius: 4px;
            color: white;
            display: inline-block;
            max-width: 80%;
            font-size: 18px;
            word-wrap: break-word;
        }

        .chatContent::-webkit-scrollbar {
            width: 8px;
        }

        .chatContent::-webkit-scrollbar-thumb {
            background: rgba(0, 0, 0, 0.5);
            border-radius: 4px;
        }

        .showChatButton {
            position: fixed;
            bottom: 6%;
            right: 4%;
            width: 52px;
            height: 42px;
            background: rgba(0, 0, 0, 0.65);
            border: none;
            border-radius: 8px;
            color: white;
            font-size: 16px;
            cursor: pointer;
            z-index: 1000002;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .showChatButton svg {
            fill: rgba(255, 255, 255, 0.9);
            width: 28px;
            height: 24px;
        }

        .redDot {
            position: absolute;
            top: 9px;
            right: 10px;
            width: 9px;
            height: 9px;
            background-color: rgba(255, 0, 0, 0.97);
            border-radius: 50%;
            display: none;
        }
    `;
    document.head.appendChild(style);
}



function initializeChatUI() {

    chatDialog = createChatDialog();
    chatDialog.style.display = 'none';

    showChatButton = document.createElement('button');
    showChatButton.className = 'showChatButton';
    showChatButton.innerHTML = `
        <svg viewBox="0 0 24 24" width="24" height="24" fill="white">
            <path d="M12 2C6.48 2 2 6.48 2 12c0 2.65 1.03 5.05 2.74 6.83L4 22l3.17-0.73C8.95 21.97 11.35 23 14 23c5.52 0 10-4.48 10-10S19.52 2 14 2zm-1 14.5v-5h-2v5h2zm4 0v-5h-2v5h2zm0-7V8h-6v1.5h6z"/>
        </svg>
        <span class="redDot"></span> <!-- Added red dot element -->
    `;
    document.body.appendChild(showChatButton);

    let rightPosition = '4%';
    let bottomPosition = '6%';

    showChatButton.style.right = rightPosition;
    showChatButton.style.bottom = bottomPosition;

    showChatButton.addEventListener('click', () => {
        if (!isDraggingShowChatButton) {
            chatDialog.style.right = rightPosition;
            chatDialog.style.bottom = bottomPosition;
            chatDialog.style.left = '';
            chatDialog.style.top = '';

            chatDialog.style.display = 'flex';
            showChatButton.style.display = 'none';

            showChatButton.querySelector('.redDot').style.display = 'none';
        }
    });

    chatDialog.querySelector('.closeChat').addEventListener('click', () => {
        const rect = chatDialog.getBoundingClientRect();
        rightPosition = `${window.innerWidth - rect.right}px`;
        bottomPosition = `${window.innerHeight - rect.bottom}px`;

        showChatButton.style.right = rightPosition;
        showChatButton.style.bottom = bottomPosition;

        chatDialog.style.display = 'none';
        showChatButton.style.display = 'block';
    });

    let isDraggingChatDialog = false;
    let dragOffsetXChatDialog, dragOffsetYChatDialog;

    chatDialog.querySelector('.chatHeader').addEventListener('mousedown', (e) => {
        isDraggingChatDialog = true;
        dragOffsetXChatDialog = e.clientX - chatDialog.offsetLeft;
        dragOffsetYChatDialog = e.clientY - chatDialog.offsetTop;
        document.addEventListener('mousemove', onDragChatDialog);
        document.addEventListener('mouseup', () => {
            isDraggingChatDialog = false;
            document.removeEventListener('mousemove', onDragChatDialog);
        });
    });

    function onDragChatDialog(e) {
        if (!isDraggingChatDialog) return;
        let x = e.clientX - dragOffsetXChatDialog;
        let y = e.clientY - dragOffsetYChatDialog;

        x = Math.max(0, Math.min(window.innerWidth - chatDialog.offsetWidth, x));
        y = Math.max(0, Math.min(window.innerHeight - chatDialog.offsetHeight, y));

        chatDialog.style.left = x + 'px';
        chatDialog.style.top = y + 'px';
        chatDialog.style.right = '';
        chatDialog.style.bottom = '';

        rightPosition = `${window.innerWidth - (x + chatDialog.offsetWidth)}px`;
        bottomPosition = `${window.innerHeight - (y + chatDialog.offsetHeight)}px`;
    }

    chatDialog.style.resize = 'both';
    chatDialog.style.overflow = 'hidden';

    let isDraggingShowChatButton = false;
    let dragOffsetXShowChatButton, dragOffsetYShowChatButton;
    let initialX, initialY;

    showChatButton.addEventListener('mousedown', (e) => {
        isDraggingShowChatButton = false;
        dragOffsetXShowChatButton = e.clientX - showChatButton.offsetLeft;
        dragOffsetYShowChatButton = e.clientY - showChatButton.offsetTop;
        initialX = e.clientX;
        initialY = e.clientY;

        document.addEventListener('mousemove', onDragShowChatButton);
        document.addEventListener('mouseup', onStopDragShowChatButton);
    });

    function onDragShowChatButton(e) {
        const moveX = e.clientX - initialX;
        const moveY = e.clientY - initialY;

        if (Math.abs(moveX) > 5 || Math.abs(moveY) > 5) {
            isDraggingShowChatButton = true;
        }

        if (isDraggingShowChatButton) {
            let x = e.clientX - dragOffsetXShowChatButton;
            let y = e.clientY - dragOffsetYShowChatButton;

            x = Math.max(0, Math.min(window.innerWidth - showChatButton.offsetWidth, x));
            y = Math.max(0, Math.min(window.innerHeight - showChatButton.offsetHeight, y));

            showChatButton.style.left = `${x}px`;
            showChatButton.style.top = `${y}px`;

            rightPosition = `${window.innerWidth - (x + showChatButton.offsetWidth)}px`;
            bottomPosition = `${window.innerHeight - (y + showChatButton.offsetHeight)}px`;

            showChatButton.style.right = rightPosition;
            showChatButton.style.bottom = bottomPosition;

            console.log('Dragging button, new position:', { rightPosition, bottomPosition });
        }
    }

    function onStopDragShowChatButton() {
        document.removeEventListener('mousemove', onDragShowChatButton);
        document.removeEventListener('mouseup', onStopDragShowChatButton);
    }

    let isResizing = false;
    let currentResizer;

    const resizers = chatDialog.querySelectorAll('.resizable');

    resizers.forEach(resizer => {
        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            currentResizer = resizer;
            document.addEventListener('mousemove', resize);
            document.addEventListener('mouseup', stopResize);
        });
    });

    function resize(e) {
        if (!isResizing) return;

        const rect = chatDialog.getBoundingClientRect();
        const maxWidth = window.innerWidth * 0.8;
        const minWidth = window.innerWidth * 0.2;
        const maxHeight = window.innerHeight * 0.8;
        const minHeight = window.innerHeight * 0.3;

        if (currentResizer.classList.contains('resizable-right')) {
            const newWidth = e.clientX - rect.left;
            chatDialog.style.width = `${Math.min(Math.max(newWidth, minWidth), maxWidth)}px`;
        } else if (currentResizer.classList.contains('resizable-bottom')) {
            const newHeight = e.clientY - rect.top;
            chatDialog.style.height = `${Math.min(Math.max(newHeight, minHeight), maxHeight)}px`;
        } else if (currentResizer.classList.contains('resizable-left')) {
            const newWidth = rect.right - e.clientX;
            if (newWidth <= maxWidth && newWidth >= minWidth) {
                chatDialog.style.width = `${newWidth}px`;
                chatDialog.style.left = `${e.clientX}px`;
            }
        } else if (currentResizer.classList.contains('resizable-top')) {
            const newHeight = rect.bottom - e.clientY;
            if (newHeight <= maxHeight && newHeight >= minHeight) {
                chatDialog.style.height = `${newHeight}px`;
                chatDialog.style.top = `${e.clientY}px`;
            }
        }
    }

    function stopResize() {
        document.removeEventListener('mousemove', resize);
        document.removeEventListener('mouseup', stopResize);
        isResizing = false;
    }

    // Ensure the chat dialog does not move when resizing beyond maximum size
    chatDialog.addEventListener('mousemove', (e) => {
        if (isResizing) {
            const rect = chatDialog.getBoundingClientRect();
            if (rect.width >= window.innerWidth * 0.8 || rect.height >= window.innerHeight * 0.8) {
                chatDialog.style.pointerEvents = 'none';
            } else {
                chatDialog.style.pointerEvents = 'auto';
            }
        }
    });

    chatDialog.addEventListener('mouseup', () => {
        chatDialog.style.pointerEvents = 'auto';
    });


    chatDialog.querySelector('.sendChat').addEventListener('click', sendMessage);
    chatDialog.querySelector('.chatInput').addEventListener('keydown', (e) => {
        const sendButton = chatDialog.querySelector('.sendChat');
        if (e.key === 'Enter' && !e.shiftKey && !sendButton.disabled) {
            e.preventDefault();
            sendMessage();
        }
    });

    function sendMessage() {
        const chatInput = chatDialog.querySelector('.chatInput');
        const sendButton = chatDialog.querySelector('.sendChat');
        const message = chatInput.value.trim();
        if (message) {
            const chatContent = chatDialog.querySelector('.chatContent');
            const messageContainer = document.createElement('div');
            messageContainer.className = 'userMessageContainer';
    
            const userMessage = document.createElement('div');
            userMessage.className = 'userMessage';
            userMessage.textContent = message;
    
            messageContainer.appendChild(userMessage);
            chatContent.appendChild(messageContainer);
    
            chatInput.value = '';
            chatContent.scrollTop = chatContent.scrollHeight;

            sendButton.disabled = true;
            sendButton.style.background = 'rgba(0, 0, 0, 0.3)';
            sendButton.style.cursor = 'not-allowed';

            const savedMessages = JSON.parse(sessionStorage.getItem('chatMessages')) || [];
            savedMessages.push({ role: 'user', text: message });
            sessionStorage.setItem('chatMessages', JSON.stringify(savedMessages));

            sendEvent('user_input', { text: message });
        }
    }
}

function displayBotMessage(text) {
    if (!chatDialog) {
        console.error('chatDialog is not defined');
        return;
    }

    const chatContent = chatDialog.querySelector('.chatContent');
    const botMessage = document.createElement('div');
    botMessage.className = 'botMessage';
    botMessage.textContent = text;
    botMessage.style.whiteSpace = 'pre-wrap';
    chatContent.appendChild(botMessage);
    chatContent.scrollTop = chatContent.scrollHeight;

    const sendButton = chatDialog.querySelector('.sendChat');
    sendButton.disabled = false;
    sendButton.style.background = 'rgba(0, 0, 0, 0.65)';
    sendButton.style.cursor = 'pointer';

    const savedMessages = JSON.parse(sessionStorage.getItem('chatMessages')) || [];
    savedMessages.push({ role: 'bot', text: text });
    sessionStorage.setItem('chatMessages', JSON.stringify(savedMessages));
}

function saveChatDialogContent() {
    const chatContent = document.querySelector('.chatContent');
    if (chatContent) {
        sessionStorage.setItem('chatDialogContent', chatContent.innerHTML);

        const savedMessages = [];
        const chatMessages = chatContent.querySelectorAll('.userMessageContainer, .botMessage');
        chatMessages.forEach(msg => {
            if (msg.classList.contains('userMessageContainer')) {
                savedMessages.push({ role: 'user', text: msg.textContent });
            } else {
                savedMessages.push({ role: 'bot', text: msg.textContent });
            }
        });
        sessionStorage.setItem('chatMessages', JSON.stringify(savedMessages));
    }
}


function restoreChatDialogContent() {
    const chatContent = document.querySelector('.chatContent');
    if (chatContent) {
        chatContent.innerHTML = ''; // Clear chat content before restoring

        const savedMessages = JSON.parse(sessionStorage.getItem('chatMessages')) || [];
        savedMessages.forEach(message => {
            if (message.role === 'user') {
                const messageContainer = document.createElement('div');
                messageContainer.className = 'userMessageContainer';

                const userMessage = document.createElement('div');
                userMessage.className = 'userMessage';
                userMessage.textContent = message.text;

                messageContainer.appendChild(userMessage);
                chatContent.appendChild(messageContainer);
            } else {
                const botMessage = document.createElement('div');
                botMessage.className = 'botMessage';
                botMessage.textContent = message.text;
                botMessage.style.whiteSpace = 'pre-wrap';

                chatContent.appendChild(botMessage);
            }
        });
        chatContent.scrollTop = chatContent.scrollHeight; // Scroll to bottom
    }
}

function handleUnloadOrVisibilityChange() {
    saveChatDialogContent();
    sendCloseEvent();
}

window.addEventListener('beforeunload', handleUnloadOrVisibilityChange);
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
        handleUnloadOrVisibilityChange();
    }
});

sessionStorage.setItem('pageLoaded', 'true');

// document.addEventListener('DOMContentLoaded', function() {
//     const isYouTube = window.location.hostname.includes('youtube.com');
//     if (isYouTube) {
//         ensureHeadAvailable(() => {
//             appendStyles();
//             ensureBodyAvailable(() => {
//                 initializeChatUI();
//                 setupEventSource();
//                 restoreChatDialogContent();
//             });
//         });
//     }
// });

function createChatDialog() {
    const chatDialog = document.createElement('div');
    chatDialog.className = 'chatDialog';
    
    const chatHeader = document.createElement('div');
    chatHeader.className = 'chatHeader';
    chatHeader.innerHTML = `<span class="chatTitle">Chatbot</span><span class="closeChat">×</span>`;
    
    const chatContent = document.createElement('div');
    chatContent.className = 'chatContent';

    const chatFooter = document.createElement('div');
    chatFooter.className = 'chatFooter';
    chatFooter.innerHTML = `<input type="text" class="chatInput" placeholder="Type a message..."><button class="sendChat">Send</button>`;
    
    chatDialog.appendChild(chatHeader);
    chatDialog.appendChild(chatContent);
    chatDialog.appendChild(chatFooter);

    // Add resizable elements to the chat dialog
    const resizableTop = document.createElement('div');
    resizableTop.className = 'resizable resizable-top';
    chatDialog.appendChild(resizableTop);

    const resizableRight = document.createElement('div');
    resizableRight.className = 'resizable resizable-right';
    chatDialog.appendChild(resizableRight);

    const resizableBottom = document.createElement('div');
    resizableBottom.className = 'resizable resizable-bottom';
    chatDialog.appendChild(resizableBottom);

    const resizableLeft = document.createElement('div');
    resizableLeft.className = 'resizable resizable-left';
    chatDialog.appendChild(resizableLeft);

    document.body.appendChild(chatDialog);

    return chatDialog;
}









// Initual customization pop-up

if (!sessionStorage.getItem('viboPopupShown')) {
    sessionStorage.setItem('viboPopupShown', 'true');

    function checkCustomizationStatus() {
        chrome.storage.sync.get(['viboCustomizationDone', 'userInfo', 'chatbotBehavior'], function(result) {
            if (result.viboCustomizationDone) {
                // Customization has already been done
                const userInfo = result.userInfo || '';
                const chatbotBehavior = result.chatbotBehavior || '';
                if (userInfo === '' && chatbotBehavior === '') {
                    sendCustomizeEvent('customize', 'no', '', '');
                } else {
                    sendCustomizeEvent('customize', 'yes', userInfo, chatbotBehavior);
                }
                playVideo();
            } else {
                // Customization not done, show the popup
                createInitialPopup();
                pauseVideo();
                setTimeout(() => {
                    pauseVideo();
                }, 2000);
        
                setTimeout(() => {
                    pauseVideo();
                }, 1000);
            }
        });
    }
    
    // Function to mark customization as done
    function markCustomizationAsDone(userInfo, chatbotBehavior) {
        chrome.storage.sync.set({ 'viboCustomizationDone': true, 'userInfo': userInfo, 'chatbotBehavior': chatbotBehavior }, function() {
            console.log('Customization data saved.');
        });
    }

    // Function to create the initial pop-up
    function createInitialPopup() {
        const overlay = document.createElement('div');
        overlay.id = 'viboInitialPopup';
        overlay.style.position = 'fixed';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '100%';
        overlay.style.height = '100%';
        overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
        overlay.style.zIndex = '1000000';
        overlay.style.display = 'flex';
        overlay.style.alignItems = 'center';
        overlay.style.justifyContent = 'center';
        overlay.style.color = 'white';
        overlay.style.flexDirection = 'column';
        overlay.innerHTML = `
            <div style="background: #A0A0A0; padding: 40px; border-radius: 20px; text-align: center; max-width: 600px; width: 100%; font-size: 20px;">
                <p>Hi! I'm Vibo, your YouTube Chatbot Assistant. Would you like to customize me to better assist you? You can also do it later by talking to me directly :)</p>
                <button id="viboYesBtn" style="background: white; color: grey; margin: 20px; padding: 15px 30px; border: none; border-radius: 10px; font-size: 18px; cursor: pointer;">Yes</button>
                <button id="viboNoBtn" style="background: white; color: grey; margin: 20px; padding: 15px 30px; border: none; border-radius: 10px; font-size: 18px; cursor: pointer;">No</button>
            </div>
        `;

        document.body.appendChild(overlay);

        document.getElementById('viboYesBtn').addEventListener('click', createCustomizationPopup);
        document.getElementById('viboNoBtn').addEventListener('click', () => {
            sendCustomizeEvent('customize', 'no', '', '');
            markCustomizationAsDone('', '');
            setTimeout(removePopup, 200);
            setTimeout(playVideo, 1000);
        });
    }

    // Function to create the customization pop-up
    function createCustomizationPopup() {
        const initialPopup = document.getElementById('viboInitialPopup');
        initialPopup.innerHTML = `
            <div style="background: #A0A0A0; padding: 40px; border-radius: 20px; text-align: center; max-width: 700px; width: 100%; font-size: 20px;">
                <div style="margin-bottom: 20px;">
                    <p>Tell me anything about you that you feel comfortable sharing, such as your name, background, interests, etc.</p>
                    <textarea id="userInfo" style="width: 100%; height: 80px; resize: none; border-radius: 10px; padding: 10px; font-size: 18px;"></textarea>
                </div>
                <div style="margin-bottom: 20px;">
                    <p>How do you want me to behave? For example, do you want me to be more chatty or quiet, warm or cool, etc.</p>
                    <textarea id="chatbotBehavior" style="width: 100%; height: 80px; resize: none; border-radius: 10px; padding: 10px; font-size: 18px;"></textarea>
                </div>
                <button id="viboDoneBtn" style="background: white; color: grey; padding: 15px 30px; border: none; border-radius: 10px; font-size: 18px; cursor: pointer;">Done</button>
            </div>
        `;

        document.getElementById('viboDoneBtn').addEventListener('click', () => {
            const userInfo = document.getElementById('userInfo').value.trim();
            const chatbotBehavior = document.getElementById('chatbotBehavior').value.trim();

            if (userInfo === '' && chatbotBehavior === '') {
                sendCustomizeEvent('customize', 'no', '', '');
                markCustomizationAsDone(userInfo, chatbotBehavior);
            } else {
                sendCustomizeEvent('customize', 'yes', userInfo, chatbotBehavior);
                markCustomizationAsDone(userInfo, chatbotBehavior);
            }

            setTimeout(removePopup, 500);
            playVideo();
        });
    }

    // Function to remove the pop-up
    function removePopup() {
        const overlay = document.getElementById('viboInitialPopup');
        if (overlay) {
            document.body.removeChild(overlay);
        }
    }

    function pauseVideo() {
        const video = document.querySelector('video');
        if (video && !video.paused) {
            video.pause();
        }
    }

    function playVideo() {
        const video = document.querySelector('video');
        if (video && video.paused) {
            video.play();
        }
    }

    // Inject styles dynamically
    function injectStyles() {
        const style = document.createElement('style');
        style.innerHTML = `
            #viboInitialPopup button {
                cursor: pointer;
            }
            #viboInitialPopup textarea {
                max-width: 100%;
                box-sizing: border-box;
                display: block;
            }
        `;
        document.head.appendChild(style);
    }

    document.addEventListener('DOMContentLoaded', () => {
        injectStyles();
        checkCustomizationStatus();
    });
}

function sendCustomizeEvent(event, value, user, chatbot) {
    const data = {
        videoId: 'customization',
        event: event,
        value: value,
        user: user,
        chatbot: chatbot
    };

    fetch('https://vibo-3137133b97c9.herokuapp.com', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    }).then(response => response.text())
      .then(result => console.log('Server response:', result))
      .catch(error => console.error('Error:', error));
}

function updateCustomization(userInfo, chatbotBehavior) {
    chrome.storage.sync.set({ 'viboCustomizationDone': true, 'userInfo': userInfo, 'chatbotBehavior': chatbotBehavior }, function() {
        console.log('Customization updated with :' + userInfo + ' and ' + chatbotBehavior);
    });
}