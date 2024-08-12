chrome.tabs.onRemoved.addListener(function(tabId, removeInfo) {

    chrome.tabs.query({}, function(tabs) {
        const youTubeTabs = tabs.filter(tab => tab.url.includes('youtube.com'));
        if (youTubeTabs.length === 0) {

            // Notify the server only if no YouTube tabs are open
            fetch('https://vibo-3137133b97c9.herokuapp.com', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    event: 'tabClose',
                    tabId: tabId
                })
            }).then(response => response.text())
              .then(result => console.log('Server response on tab close:', result))
              .catch(error => console.error('Error on sending tab close event:', error));
        }
    });
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'checkYouTubeTabs') {
        chrome.tabs.query({}, function(tabs) {
            const youTubeTabs = tabs.filter(tab => tab.url.includes('youtube.com'));
            if (youTubeTabs.length === 1) {
                sendResponse({ noYouTubeTabs: true });
            } else {
                sendResponse({ noYouTubeTabs: false });
            }
        });
        // Returning true indicates that the response is sent asynchronously
        return true;
    }
});