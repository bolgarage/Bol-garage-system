/* ==========================================================
   Bol Garage mockup - sample data
   Everything here is placeholder data. In the real system
   this comes from the database (Django models).
   ========================================================== */

window.BOL = {
  cars: [
    { id: 1,  brand: 'Toyota',     name: 'Toyota Vios 1.3 E',            year: 2018, km: 58000,  trans: 'Automatic', fuel: 'Gasoline', status: 'Available',    bought: 395000, spent: 28000, price: 465000,  days: 18 },
    { id: 2,  brand: 'Honda',      name: 'Honda Civic 1.8 S',            year: 2017, km: 71000,  trans: 'Automatic', fuel: 'Gasoline', status: 'Available',    bought: 490000, spent: 51000, price: 598000,  days: 52 },
    { id: 3,  brand: 'Mitsubishi', name: 'Mitsubishi Montero Sport GLS', year: 2016, km: 96000,  trans: 'Automatic', fuel: 'Diesel',   status: 'Reserved',     bought: 690000, spent: 45000, price: 820000,  days: 74 },
    { id: 4,  brand: 'Toyota',     name: 'Toyota Fortuner G',            year: 2019, km: 44000,  trans: 'Automatic', fuel: 'Diesel',   status: 'Available',    bought: 960000, spent: 70000, price: 1150000, days: 41 },
    { id: 5,  brand: 'Nissan',     name: 'Nissan Almera 1.5 V',          year: 2019, km: 39000,  trans: 'Automatic', fuel: 'Gasoline', status: 'Available',    bought: 420000, spent: 32000, price: 510000,  days: 33 },
    { id: 6,  brand: 'Suzuki',     name: 'Suzuki Ertiga GLX',            year: 2020, km: 31000,  trans: 'Automatic', fuel: 'Gasoline', status: 'Available',    bought: 465000, spent: 24000, price: 560000,  days: 12 },
    { id: 7,  brand: 'Honda',      name: 'Honda City 1.5 E',             year: 2018, km: 62000,  trans: 'Automatic', fuel: 'Gasoline', status: 'Reserved',     bought: 410000, spent: 18000, price: 485000,  days: 27 },
    { id: 8,  brand: 'Mitsubishi', name: 'Mitsubishi Xpander GLS',       year: 2019, km: 47000,  trans: 'Automatic', fuel: 'Gasoline', status: 'Available',    bought: 540000, spent: 36000, price: 640000,  days: 21 },
    { id: 9,  brand: 'Mazda',      name: 'Mazda 3 Sedan',                year: 2016, km: 88000,  trans: 'Automatic', fuel: 'Gasoline', status: 'Under repair', bought: 430000, spent: 15000, price: 520000,  days: 8 },
    { id: 10, brand: 'Toyota',     name: 'Toyota Innova E',              year: 2017, km: 79000,  trans: 'Manual',    fuel: 'Diesel',   status: 'Under repair', bought: 560000, spent: 22000, price: 680000,  days: 5 },
    { id: 11, brand: 'Hyundai',    name: 'Hyundai Accent 1.4 GL',        year: 2018, km: 65000,  trans: 'Manual',    fuel: 'Gasoline', status: 'Incoming',     bought: 360000, spent: 0,     price: 0,       days: 2 },
    { id: 12, brand: 'Ford',       name: 'Ford Ranger XLT',              year: 2016, km: 102000, trans: 'Manual',    fuel: 'Diesel',   status: 'Incoming',     bought: 720000, spent: 0,     price: 0,       days: 1 },
    { id: 13, brand: 'Suzuki',     name: 'Suzuki Ertiga GL',             year: 2018, km: 70000,  trans: 'Manual',    fuel: 'Gasoline', status: 'Sold',         bought: 380000, spent: 20000, price: 475000,  days: 36 },
    { id: 14, brand: 'Nissan',     name: 'Nissan Navara EL',             year: 2017, km: 83000,  trans: 'Manual',    fuel: 'Diesel',   status: 'Sold',         bought: 610000, spent: 42000, price: 735000,  days: 48 },
    { id: 15, brand: 'Toyota',     name: 'Toyota Hilux G',               year: 2015, km: 110000, trans: 'Manual',    fuel: 'Diesel',   status: 'Sold',         bought: 520000, spent: 38000, price: 640000,  days: 29 }
  ],

  // Cars the Vios (id 1) detail page and admin page show
  viosExpenses: [
    { date: 'Oct 10', item: 'Oil change and filters',          cat: 'Repair',       amount: 3500 },
    { date: 'Oct 12', item: 'Front brake pads',                cat: 'Parts',        amount: 6500 },
    { date: 'Oct 15', item: 'Paint touch-up',                  cat: 'Paint',        amount: 9000 },
    { date: 'Oct 18', item: 'Registration renewal',            cat: 'Registration', amount: 5000 },
    { date: 'Oct 22', item: 'Interior and exterior detailing', cat: 'Cleaning',     amount: 4000 }
  ],

  documents: [
    { name: 'OR/CR',                      file: 'vios-or-cr.pdf',        uploaded: true },
    { name: 'Deed of sale (from seller)', file: 'vios-deed-of-sale.pdf', uploaded: true },
    { name: 'Repair receipts',            file: '3 files',               uploaded: true },
    { name: 'Deed of sale (to buyer)',    file: 'Not yet',               uploaded: false }
  ],

  profitByMonth: [
    { month: 'May', value: 148 },
    { month: 'Jun', value: 96 },
    { month: 'Jul', value: 175 },
    { month: 'Aug', value: 131 },
    { month: 'Sep', value: 188 },
    { month: 'Oct', value: 212 }
  ],

  inquiries: [
    { id: 1, who: 'Maria Santos',  contact: 'maria.santos@example.com · 09XX XXX XXXX',  car: 'Toyota Vios 1.3 E',            kind: 'Inquiry',         when: '2 hours ago', status: 'New',       message: 'Hi, is this Toyota Vios still available? I would like to view it this week.' },
    { id: 2, who: 'Jun Reyes',     contact: 'jun.reyes@example.com · 09XX XXX XXXX',     car: 'Honda Civic 1.8 S',            kind: 'Reserve request', when: 'Yesterday',   status: 'New',       message: 'I would like to reserve the Civic. I can come to the garage on Saturday with cash.' },
    { id: 3, who: 'Ana Cruz',      contact: 'ana.cruz@example.com · 09XX XXX XXXX',      car: 'Suzuki Ertiga GLX',            kind: 'Inquiry',         when: 'Yesterday',   status: 'New',       message: 'Is the price negotiable? Also, can I bring my mechanic to check the car?' },
    { id: 4, who: 'Paolo Garcia',  contact: 'paolo.garcia@example.com · 09XX XXX XXXX',  car: 'Toyota Fortuner G',            kind: 'Inquiry',         when: '2 days ago',  status: 'New',       message: 'Can I view the Fortuner on Saturday morning?' },
    { id: 5, who: 'Liza Ramos',    contact: 'liza.ramos@example.com · 09XX XXX XXXX',    car: 'Nissan Almera 1.5 V',          kind: 'Inquiry',         when: '4 days ago',  status: 'Contacted', message: 'What is the lowest price for the Almera?' },
    { id: 6, who: 'Carlo Mendoza', contact: 'carlo.mendoza@example.com · 09XX XXX XXXX', car: 'Mitsubishi Montero Sport GLS', kind: 'Reserve request', when: '1 week ago',  status: 'Closed',    message: 'I want to reserve the Montero Sport for this weekend.' }
  ]
};
