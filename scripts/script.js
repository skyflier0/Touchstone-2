function calculateTotal(price, tax) {
    return price + tax;
}

let price = 100;
let tax = 15;

let total = calculateTotal(price, tax);
console.log("Total amount: $" + total);

function calculateTotal(price, tax) {
    // if the order is over $50, no tax — return just price
    if (price > 50) {
        return price;
    }
    // otherwise return price + tax
    else {
        return price + tax;
    }
}
