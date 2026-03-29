export function init(){
	sessionStorage.setItem('inputs',"");

	const textInputs = document.querySelectorAll('input.disappearing');
	textInputs.forEach(input => {
		registerSearchBar(input.id);
		document.querySelector(`#${input.id}`).addEventListener("click", (event =>{
			clearSearchBar(input.id);
		}));
		
	});

	// document.querySelector('#product-search').addEventListener("click", (event =>{
	// 	clearSearchBar('#product-search');
	// }));
	document.addEventListener("click", (event => {	
		globalEventHandler(event);
	}));
}
export function exit(){
	sessionStorage.clear();
}

function globalEventHandler(event){
	if(event.target.classList.contains('disappearing')){
		return;
	}
	restoreSearchBar("product-search");
}

function registerSearchBar(id){
	let val = document.querySelector(`#${id}`).value;

	if(val !== ""){
		sessionStorage.setItem(id, val);
		
	}
}
export function clearSearchBar(id){
	let val = document.querySelector(`#${id}`).value;
	if(val != ""){
		document.querySelector(`#${id}`).value = "";
	}
}

function restoreSearchBar(id){
	const output = sessionStorage.getItem(`${id}`);
	document.querySelector(`#${id}`).value = output;
}
