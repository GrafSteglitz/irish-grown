/**
 * Initialize the form listener.
 */
export function init() {
//	const forms = document.querySelector("form");
	const t1 = document.querySelector("#t0").content.cloneNode(true);
	const t2 = document.querySelector("#t1").content.cloneNode(true);
	window.myTemplates = [t1,t2];
	window.myTemplatePointer = 0;
	displayTemplate(window.myTemplatePointer);
//	window.myForms = forms;
//		if (forms) {
//			for(let each of forms){
//			// Correctly wrapping the async event listener
//            each.addEventListener("submit", async (event) => {
//                event.preventDefault();
//                await submitForm('/onboarding_1');
//            });
//            }
//            displayForm();
//  }
}
function displayTemplate(pointer){
	let output = document.querySelector('#form-display');
	output.appendChild(window.myTemplates[pointer]);
	const formID = `#form-t${pointer}`;
	let form = document.querySelector(formID);
	form.addEventListener("submit", async (event) => {
                event.preventDefault();
                await submitForm('/create_account',formID);
            });
	window.myTemplatePointer += 1;

}

/**
 * Handles the async POST request for the form.
 */
async function submitForm(route, formID) {
	const myForm = document.querySelector(`${formID}`);
	const output = document.querySelector("#output");
	const formData = new FormData(myForm);

	try {
	// ERROR FIX 1: The options object must be INSIDE the fetch parentheses.
	// ERROR FIX 2: When sending JSON, you MUST set the Content-Type header.
	const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
	const response = await fetch(route, {
	  method: "POST",
	  headers: {
	    "Content-Type": "application/json",
	    "X-CSRFToken": csrfToken
	  },
	  body: JSON.stringify(Object.fromEntries(formData.entries())),
	});

	if (!response.ok) {
	  throw new Error(`HTTP error! status: ${response.status}`);
	}

	// ERROR FIX 3: fetch returns a response object. You must await the JSON parsing.
	const results = await response.json();

	// ERROR FIX 4: Assuming your server returns an object like { html: "..." }
	// Note: 'response.html' doesn't exist; you need the parsed 'results.html'.
	if (output && results) {
	  showFormErrors(results);
	  if(results.status === "success"){
		displayTemplate(window.myTemplatePointer);
	  }
	}
	} catch (error) {
	// ERROR FIX 5: Added the 'error' parameter to catch block so console.error works.
	console.error("Error submitting form:", error);
	}
}

/**
 * Utility to prevent default behavior (like Enter key submission).
 */
function preventEnter(event) {
  if (event.key === "Enter") {
    event.preventDefault();
    return false;
  }
}

function showFormErrors(errorFeedback){
	const errors = document.querySelectorAll('.form-error');

	errors.forEach(error => {
	if (error.checkVisibility()) {
		// This element is truly visible to the user
		error.innerHTML = `${errorFeedback.status}: ${errorFeedback.message}`
	}
	});
}