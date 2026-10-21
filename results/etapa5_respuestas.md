# Etapa 5 - Respuestas del modelo con el contexto seleccionado

Modelo: `deepset/roberta-base-squad2` (extractivo, sin entrenamiento adicional), con la lógica de `ask_question` del cuaderno PokeChat: si `score_difference` < 0.5, la respuesta es "I don't know" (el PokeChat usaba 7; el umbral se calibró con `calibrar_umbral.py`). Flujo: pregunta → búsqueda → recuperación de los 10 mejores fragmentos → selección del contexto (`greedy`, con eliminación de redundancia) → el modelo lee cada fragmento elegido por separado y se queda con la respuesta de mayor `score_difference` → respuesta.

Método principal: búsqueda aproximada híbrida. En paralelo: búsqueda exacta (KMP con índice). 24 preguntas del banco de Ana: 10 literal, 4 paraphrase, 6 typo, 4 no_answer, repartidas uniformemente dentro de cada categoría. Tiempos medidos sin caché del modelo, en CPU.

## Criterios del diagnóstico automático

- **Evidencia en el contexto**: algún fragmento relevante de Ana (`relevant_chunks`) quedó entre los seleccionados.
- **Correcta**: F1 ≥ 0.5 contra las respuestas aceptadas del banco (EM/F1 de `answer_scores`).
- **correcta y respaldada**: correcta y con evidencia en el contexto.
- **correcta (evidencia fuera de los fragmentos anotados)**: correcta, pero salió de un fragmento que no está entre los relevantes de Ana (otro documento dice lo mismo).
- **recuperación incompleta**: incorrecta y la evidencia no llegó al contexto.
- **falla del modelo**: incorrecta aunque la evidencia sí estaba en el contexto.
- **no-respuesta correcta / respuesta sin respaldo**: pregunta sin respuesta en la colección; el modelo dice o no dice "I don't know".

## Resumen por diagnóstico

| Diagnóstico | Aproximada (híbrida) | Exacta (KMP) |
|---|---:|---:|
| correcta y respaldada | 13 | 10 |
| correcta (evidencia fuera de los fragmentos anotados) | 0 | 0 |
| recuperación incompleta | 5 | 7 |
| falla del modelo | 2 | 3 |
| no-respuesta correcta | 4 | 4 |
| respuesta sin respaldo | 0 | 0 |

| Método | EM | F1 | Evidencia en contexto | "I don't know" | Truncadas | Tokens de entrada prom. | Búsqueda ms | Selección ms | Modelo ms | Total ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Aproximada (híbrida) | 0.708 | 0.708 | 15/20 | 9/24 | 0 | 168 | 5.9 | 5.8 | 540 | 552 |
| Exacta (KMP) | 0.583 | 0.597 | 13/20 | 11/24 | 0 | 161 | 22.9 | 2.8 | 553 | 579 |

**"I don't know" con el tramo correcto:** en 0 preguntas (aproximada) y 0 (exacta) el modelo eligió el tramo correcto, pero su score_difference quedó debajo del umbral 0.5 del PokeChat. La columna `raw_answer` del `.csv` guarda ese tramo. El efecto del tamaño del contexto sobre score_difference se mide en la Etapa 6.

EM y F1 son promedios sobre las 24 preguntas (las sin respuesta valen 1 si el modelo dice "I don't know"). La evidencia en contexto se cuenta solo en las 20 preguntas con respuesta.

## Tabla de respuestas

| Id | Categoría | Pregunta | Esperada | Aproximada: respuesta (score_diff) | Diagnóstico | Exacta: respuesta (score_diff) | Diagnóstico |
|---|---|---|---|---|---|---|---|
| Q01 | literal | When was Pluto discovered? | 1930 | 1930 (8.88) | correcta y respaldada | 1930 (8.88) | correcta y respaldada |
| Q05 | literal | How many known moons does Pluto have? | five, five known moons | five (5.78) | correcta y respaldada | five (5.78) | correcta y respaldada |
| Q09 | literal | How long is a year on Mars? | 687 Earth days, 669.6 sols | I don't know (0.00) | recuperación incompleta | I don't know (0.00) | recuperación incompleta |
| Q14 | literal | Who discovered Uranus? | William Herschel, Herschel | William Herschel (11.24) | correcta y respaldada | William Herschel (11.24) | correcta y respaldada |
| Q18 | literal | What is the largest moon of Neptune? | Triton | Triton (9.70) | correcta y respaldada | Triton (9.70) | correcta y respaldada |
| Q22 | literal | What is the atmosphere of Venus mostly made of? | carbon dioxide | carbon dioxide (11.05) | correcta y respaldada | carbon dioxide (11.05) | correcta y respaldada |
| Q26 | literal | Which planet has an average density less than water? | Saturn | Saturn (4.58) | correcta y respaldada | Saturn (4.58) | correcta y respaldada |
| Q30 | literal | What lies beneath the icy shell of Europa? | a saltwater ocean, saltwater ocean | saltwater ocean (10.25) | correcta y respaldada | saltwater ocean (10.25) | correcta y respaldada |
| Q35 | literal | How far is the Sun from Earth? | 93 million miles (150 million kilometers), 93 million miles, 150 million kilometers | 60 times (1.14) | recuperación incompleta | 60 times (1.14) | recuperación incompleta |
| Q39 | literal | Who led the committee that selected the contents of the golden record? | Carl Sagan | Carl Sagan (9.54) | correcta y respaldada | Carl Sagan (9.54) | correcta y respaldada |
| Q43 | paraphrase | Which world circles closest to our star? | Mercury | Io (4.21) | recuperación incompleta | Io (4.21) | recuperación incompleta |
| Q45 | paraphrase | What is the tallest volcano on the red planet? | Olympus Mons | I don't know (0.00) | recuperación incompleta | I don't know (0.00) | recuperación incompleta |
| Q47 | paraphrase | What enormous storm rages on the biggest planet? | Great Red Spot | Great Red Spot (1.69) | correcta y respaldada | Great Red Spot (1.69) | correcta y respaldada |
| Q49 | paraphrase | Which moon of the ringed planet has seas of hydrocarbons? | Titan | Titan (0.71) | correcta y respaldada | Titan (0.71) | correcta y respaldada |
| Q01-T | typo | When was Pluot discovered? | 1930 | 1930 (8.46) | correcta y respaldada | I don't know (0.00) | recuperación incompleta |
| Q10-T | typo | What is the Graet Red Spot? | a giant storm bigger than Earth, giant storm | I don't know (0.00) | falla del modelo | I don't know (0.00) | falla del modelo |
| Q17-T | typo | When was Neptue discovered? | 1846 | 1846 (5.44) | correcta y respaldada | I don't know (0.00) | falla del modelo |
| Q25-T | typo | What are Saturn's rinngs made of? | billions of small chunks of ice and rock, ice and rock | billions of small chunks of ice and rock (11.76) | correcta y respaldada | hydrogen and helium (6.98) | recuperación incompleta |
| Q35-T | typo | How far is the Sun from Earht? | 93 million miles (150 million kilometers), 93 million miles, 150 million kilometers | I don't know (0.00) | recuperación incompleta | I don't know (0.00) | recuperación incompleta |
| Q42-T | typo | Where do comeos come from? | the Kuiper Belt and the Oort Cloud, Kuiper Belt, Oort Cloud | I don't know (0.00) | falla del modelo | I don't know (0.00) | falla del modelo |
| Q51 | no_answer | How many people live on Mars today? | — | I don't know (0.00) | no-respuesta correcta | I don't know (0.00) | no-respuesta correcta |
| Q53 | no_answer | How much does a ticket to the Moon cost? | — | I don't know (0.00) | no-respuesta correcta | I don't know (0.00) | no-respuesta correcta |
| Q54 | no_answer | Who is the current president of Jupiter? | — | I don't know (0.00) | no-respuesta correcta | I don't know (0.00) | no-respuesta correcta |
| Q55 | no_answer | What is the favorite food of astronauts on Pluto? | — | I don't know (0.00) | no-respuesta correcta | I don't know (0.00) | no-respuesta correcta |

## Detalle por pregunta (búsqueda aproximada híbrida)

### Q01 [literal] When was Pluto discovered?

- Respuestas aceptadas: 1930; fragmentos relevantes: [386, 389]
- Correcciones: ninguna
- **Respuesta: 1930** · score_difference = 8.88 · fragmento de origen: 240 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 3 fragmentos, 483 tokens de 495 disponibles; entrada al modelo 180/512
- Tiempos: búsqueda 1.0 ms · selección 1.9 ms · modelo 491 ms · total 494 ms
- Exacta (KMP): 1930 (8.88) · correcta y respaldada · fragmentos [240, 389, 47]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 240 ← respuesta | Kuiper Belt Facts > Pluto's Place in the Kuiper Belt | 173 | no | In 1930, **Pluto** became the first Kuiper Belt object to be **discovered**. It was found at a time before astronomers had reason to expect a large population of icy worlds beyond Neptune. Today it's known as the "King of the Kuiper Belt" – and it's the largest object in the region, even though another object similar in size, called Eris, has a sli… |
| 2 | 389 | Pluto Facts > Namesake | 156 | sí | In 1930, Venetia Burney of Oxford, England, suggested to her grandfather that the new discovery be named for the Roman god of the underworld. He forwarded the name to the Lowell Observatory and it was selected. In an interview with NASA in January 2006, Venetia said she offered the name **Pluto** over breakfast with her mother and grandfather. It w… |
| 3 | 47 | Ceres Facts > Introduction / Namesake | 156 | no | Dwarf planet Ceres is the largest object in the asteroid belt between Mars and Jupiter, and it's the only dwarf planet located in the inner solar system. It was the first member of the asteroid belt to be **discovered** when Giuseppe Piazzi spotted it in 1801. When NASA's Dawn arrived in 2015, Ceres became the first dwarf planet to receive a visit … |

Descartados: 386 (no cabe en el presupuesto (184 tokens)); 395 (no cabe en el presupuesto (188 tokens)); 396 (no cabe en el presupuesto (181 tokens)); 392 (no cabe en el presupuesto (147 tokens)); 390 (no cabe en el presupuesto (168 tokens)); 388 (no cabe en el presupuesto (143 tokens)); 393 (no cabe en el presupuesto (182 tokens))

### Q05 [literal] How many known moons does Pluto have?

- Respuestas aceptadas: five, five known moons; fragmentos relevantes: [387, 388, 395]
- Correcciones: ninguna
- **Respuesta: five** · score_difference = 5.78 · fragmento de origen: 388 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 4 fragmentos, 373 tokens de 492 disponibles; entrada al modelo 153/512
- Tiempos: búsqueda 11.4 ms · selección 4.5 ms · modelo 453 ms · total 469 ms
- Exacta (KMP): five (5.78) · correcta y respaldada · fragmentos [388, 399, 424, 339]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 388 ← respuesta | Pluto Facts > Introduction | 143 | sí | It's about 3.6 billion miles away from the Sun, and it has a thin atmosphere composed mostly of nitrogen, methane, and carbon monoxide. On average, **Pluto’s** temperature is -387°F (-232°C), making it too cold to sustain life. **Pluto** is orbited by five known **moons**, the largest of which is Charon. Charon is about half the size of **Pluto** i… |
| 2 | 399 | Pluto Facts > Structure | 62 | no | **Pluto** is about two-thirds the diameter of Earth's **Moon** and probably has a rocky core surrounded by a mantle of water ice. Interesting ices like methane and nitrogen frost coat the surface. Due to its lower density, **Pluto's** mass is about one-sixth that of Earth's **Moon**.… |
| 3 | 424 | Solar System Facts > Moons | 134 | no | In addition to Earth's **Moon**, our solar system has hundreds of **moons** orbiting planets, dwarf planets, and asteroids. Of the eight planets, Mercury and Venus are the only ones with no **moons**, although Venus does have a quasi-satellite that has officially been named Zoozve. The giant planets Jupiter and Saturn lead our solar system’s **moon… |
| 4 | 339 | New Horizons Mission > Firsts | 36 | no | First spacecraft to explore **Pluto** and its **moons** up close. First spacecraft to explore a second Kuiper Belt Object up close – Arrokoth (2014 MU69)… |

Descartados: 395 (no cabe en el presupuesto (188 tokens)); 396 (no cabe en el presupuesto (181 tokens)); 392 (no cabe en el presupuesto (147 tokens)); 387 (no cabe en el presupuesto (195 tokens)); 347 (no cabe en el presupuesto (163 tokens)); 350 (no cabe en el presupuesto (188 tokens))

### Q09 [literal] How long is a year on Mars?

- Respuestas aceptadas: 687 Earth days, 669.6 sols; fragmentos relevantes: [270]
- Correcciones: ninguna
- **Respuesta: I don't know** · score_difference = 0.00 · fragmento de origen: — · EM 0, F1 0.00 · **recuperación incompleta** · tramo incorrecto (vacío)
- Contexto: 7 fragmentos, 475 tokens de 492 disponibles; entrada al modelo 142/512
- Tiempos: búsqueda 14.9 ms · selección 6.2 ms · modelo 563 ms · total 584 ms
- Exacta (KMP): I don't know (0.00) · recuperación incompleta · fragmentos [327, 279, 256, 268, 252, 67, 369]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 327 | Neptune Facts > Orbit and Rotation | 74 | no | Neptune’s axis of rotation is tilted 28 degrees with respect to the plane of its orbit around the Sun, which is similar to the axial tilts of **Mars** and Earth. This means that Neptune experiences seasons just like we do on Earth; however, since its **year** is so **long**, each of the four seasons lasts for over 40 **years**.… |
| 2 | 279 | Mars Facts > Water on Mars | 132 | no | **Mars** appears to have had a watery past, with ancient river valley networks, deltas, and lakebeds, as well as rocks and minerals on the surface that could only have formed in liquid water. Some features suggest that **Mars** experienced huge floods about 3.5 billion **years** ago. There is water on **Mars** today, but the Martian atmosphere is t… |
| 3 | 256 | Mars Exploration > MARS RECONNAISSANCE ORBITER / Active Mission | 41 | no | **Mars** Reconnaissance Orbiter searches for evidence that water persisted on the surface of **Mars** for a **long** period of time. Launch: Aug. 12, 2005 **Mars** Arrival: **Mar**. 10, 2006… |
| 4 | 268 | Mars Facts > Potential for Life | 38 | no | Scientists don't expect to find living things currently thriving on **Mars**. Instead, they're looking for signs of life that existed **long** ago, when **Mars** was warmer and covered with water.… |
| 5 | 252 | Mars Exploration > Viking@50 Downloads | 42 | no | The lander that broke ground on 50 **years** of **Mars** surface exploration. Celebrate Viking — and the missions still building on what it began — with posters, computer backdrops, phone screens and more.… |
| 6 | 369 | Oort Cloud Facts > Home to Comets | 66 | no | (Hence the name.) Countless more unknown **long**-period comets have never been seen by human eyes. Some have orbits so **long** that the last time they passed through the inner solar system, our species did not yet exist. Others have never ventured close to the Sun in the billions of **years** since they formed.… |
| 7 | 67 | Curiosity Mission > Curiosity Reaches 1-Kilometer Elevation Gain / NAS | 84 | no | NASA’s Curiosity **Mars** rover reached the pinnacle — so far — of its 14-**year**-old mission on Aug. 26, 2026, when it marked an elevation gain of 1 kilometer in its journey from Gale Crater on **Mars** up the slope of Mount Sharp. After **years** of lab work, the results are in: A rock that NASA’s Curiosity **Mars** rover drilled and analyzed in… |

Descartados: 368 (no cabe en el presupuesto (191 tokens)); 270 (no cabe en el presupuesto (188 tokens)); 271 (no cabe en el presupuesto (111 tokens))

### Q14 [literal] Who discovered Uranus?

- Respuestas aceptadas: William Herschel, Herschel; fragmentos relevantes: [467, 468]
- Correcciones: ninguna
- **Respuesta: William Herschel** · score_difference = 11.24 · fragmento de origen: 467 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 5 fragmentos, 453 tokens de 495 disponibles; entrada al modelo 149/512
- Tiempos: búsqueda 1.7 ms · selección 6.0 ms · modelo 483 ms · total 491 ms
- Exacta (KMP): William Herschel (11.24) · correcta y respaldada · fragmentos [467, 323, 466, 472, 476]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 467 ← respuesta | Uranus Facts > Introduction | 133 | sí | **Uranus** is a very cold and windy world. The ice giant is surrounded by 13 faint rings and 28 small moons. **Uranus** rotates at a nearly 90-degree angle from the plane of its orbit. This unique tilt makes **Uranus** appear to spin sideways, orbiting the Sun like a rolling ball. **Uranus** was the first planet found with the aid of a telescope. I… |
| 2 | 323 | Neptune Facts > Discovery and Namesake | 142 | no | Galileo recorded Neptune as a fixed star during observations with his small telescope in 1612 and 1613. More than 200 years later, the ice giant became the first planet located through mathematical predictions rather than through regular observations of the sky. Because **Uranus** didn't travel exactly as astronomers expected it to, French mathemat… |
| 3 | 466 | Uranus Facts > Our Solar System | 34 | no | **Uranus** is the seventh planet from the Sun, and it has the third largest diameter of planets in our solar system. **Uranus** appears to spin sideways.… |
| 4 | 472 | Uranus Facts > Moons | 82 | no | **Uranus** has 28 known moons. While most of the satellites orbiting other planets take their names from Greek or Roman mythology, **Uranus**' moons are unique in being named for characters from the works of William Shakespeare and Alexander Pope. All of **Uranus**' inner moons appear to be roughly half water ice and half rock. The composition of t… |
| 5 | 476 | Uranus Facts > Surface | 64 | no | As an ice giant, **Uranus** doesn’t have a true surface. The planet is mostly swirling fluids. While a spacecraft would have nowhere to land on **Uranus**, it wouldn’t be able to fly through its atmosphere unscathed either. The extreme pressures and temperatures would destroy a metal spacecraft.… |

Descartados: 240 (no cabe en el presupuesto (173 tokens)); 478 (no cabe en el presupuesto (151 tokens)); 471 (no cabe en el presupuesto (186 tokens)); 470 (no cabe en el presupuesto (118 tokens)); 477 (no cabe en el presupuesto (179 tokens))

### Q18 [literal] What is the largest moon of Neptune?

- Respuestas aceptadas: Triton; fragmentos relevantes: [323, 328, 329, 461, 462, 463, 464, 465]
- Correcciones: ninguna
- **Respuesta: Triton** · score_difference = 9.70 · fragmento de origen: 328 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 3 fragmentos, 348 tokens de 492 disponibles; entrada al modelo 183/512
- Tiempos: búsqueda 3.0 ms · selección 5.4 ms · modelo 444 ms · total 452 ms
- Exacta (KMP): Triton (9.70) · correcta y respaldada · fragmentos [328, 323, 456]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 328 ← respuesta | Neptune Facts > Moons | 173 | sí | **Neptune** has 16 known **moons**. **Neptune's** **largest** **moon** Triton was discovered on Oct. 10, 1846, by William Lassell, just 17 days after Johann Gottfried Galle discovered the planet. Since **Neptune** was named for the Roman god of the sea, its **moons** are named for various lesser sea gods and nymphs in Greek mythology. Triton is the… |
| 2 | 323 | Neptune Facts > Discovery and Namesake | 142 | sí | Galileo recorded **Neptune** as a fixed star during observations with his small telescope in 1612 and 1613. More than 200 years later, the ice giant became the first planet located through mathematical predictions rather than through regular observations of the sky. Because Uranus didn't travel exactly as astronomers expected it to, French mathemat… |
| 3 | 456 | Titan Facts > La NASA refuerza Artemis: añade una misión y perfecciona | 35 | no | Titan is Saturn’s **largest** **moon**. It has an earthlike cycle of liquids flowing across its surface. It is the only **moon** with a thick atmosphere.… |

Descartados: 462 (no cabe en el presupuesto (187 tokens)); 387 (no cabe en el presupuesto (195 tokens)); 116 (no cabe en el presupuesto (162 tokens)); 204 (no cabe en el presupuesto (189 tokens)); 167 (no cabe en el presupuesto (183 tokens)); 240 (no cabe en el presupuesto (173 tokens)); 383 (no cabe en el presupuesto (205 tokens))

### Q22 [literal] What is the atmosphere of Venus mostly made of?

- Respuestas aceptadas: carbon dioxide; fragmentos relevantes: [501]
- Correcciones: ninguna
- **Respuesta: carbon dioxide** · score_difference = 11.05 · fragmento de origen: 501 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 5 fragmentos, 485 tokens de 490 disponibles; entrada al modelo 186/512
- Tiempos: búsqueda 6.2 ms · selección 8.6 ms · modelo 621 ms · total 636 ms
- Exacta (KMP): carbon dioxide (11.05) · correcta y respaldada · fragmentos [501, 333, 295, 483, 412]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 501 ← respuesta | Venus Facts > Atmosphere | 124 | sí | **Venus**’ **atmosphere** is one of extremes. With the hottest surface in the solar system, apart from the Sun itself, **Venus** is hotter even than the innermost planet, charbroiled Mercury. The **atmosphere** is **mostly** carbon dioxide — the same gas drives the greenhouse effect on both **Venus** and Earth — with dense clouds composed of sulfur… |
| 2 | 333 | Neptune Facts > Surface | 54 | no | Neptune does not have a solid surface. Its **atmosphere** (**made** up **mostly** of hydrogen, helium, and methane) extends to great depths, gradually merging into water and other melted ices over a heavier, solid core with about the same mass as Earth.… |
| 3 | 295 | Mercury Facts > Atmosphere | 49 | no | Instead of an **atmosphere**, Mercury possesses a thin exosphere **made** up of atoms blasted off the surface by the solar wind and striking meteoroids. Mercury's exosphere is composed **mostly** of oxygen, sodium, hydrogen, helium, and potassium.… |
| 4 | 483 | Venus Facts > Potential for Life | 174 | no | The most likely explanations focus on fine particles, ice crystals, or even a chemical compound called iron chloride. Although it's much less likely, another possibility considered by scientists who study astrobiology is that these streaks could be **made** up of microbial life, **Venus**-style. Astrobiologists note that ring-shaped linkages of sul… |
| 5 | 412 | Saturn Facts > Formation | 86 | no | Saturn took shape when the rest of the solar system formed about 4.5 billion years ago when gravity pulled swirling gas and dust in to become this gas giant. About 4 billion years ago, Saturn settled into its current position in the outer solar system, where it is the sixth planet from the Sun. Like Jupiter, Saturn is **mostly** **made** of hydroge… |

Descartados: 498 (no cabe en el presupuesto (184 tokens)); 280 (no cabe en el presupuesto (168 tokens)); 482 (no cabe en el presupuesto (192 tokens)); 207 (no cabe en el presupuesto (145 tokens)); 334 (no cabe en el presupuesto (176 tokens))

### Q26 [literal] Which planet has an average density less than water?

- Respuestas aceptadas: Saturn; fragmentos relevantes: [413]
- Correcciones: ninguna
- **Respuesta: Saturn** · score_difference = 4.58 · fragmento de origen: 413 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 4 fragmentos, 411 tokens de 490 disponibles; entrada al modelo 150/512
- Tiempos: búsqueda 6.2 ms · selección 7.4 ms · modelo 463 ms · total 477 ms
- Exacta (KMP): Saturn (4.58) · correcta y respaldada · fragmentos [413, 308, 52, 399]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 413 ← respuesta | Saturn Facts > Structure | 110 | sí | Like Jupiter, Saturn is made mostly of hydrogen and helium. At Saturn's center is a dense core of metals like iron and nickel surrounded by rocky material and other compounds solidified by intense pressure and heat. It is enveloped by liquid metallic hydrogen inside a layer of liquid hydrogen –similar to Jupiter's core but considerably smaller. It'… |
| 2 | 308 | Moon Facts > Size and Distance | 103 | no | With a radius of about 1,080 miles (1,740 kilometers), the Moon is **less** than a third of the width of Earth. If Earth were the size of a nickel, the Moon would be about as big as a coffee bean. The Moon is an **average** of 238,855 miles (384,400 kilometers) away. That means 30 Earth-sized **planets** could fit in between Earth and the Moon. The… |
| 3 | 52 | Ceres Facts > Structure | 138 | no | Ceres is more similar to the terrestrial **planets** (Mercury, Venus, Earth, and Mars) than its asteroid neighbors, but it is much **less** dense. One of the similarities is a layered interior, but Ceres' layers aren’t as clearly defined. Ceres probably has a solid core and a mantle made of **water** ice. In fact, Ceres could be composed of as much… |
| 4 | 399 | Pluto Facts > Structure | 62 | no | Pluto is about two-thirds the diameter of Earth's Moon and probably has a rocky core surrounded by a mantle of **water** ice. Interesting ices like methane and nitrogen frost coat the surface. Due to its lower **density**, Pluto's mass is about one-sixth that of Earth's Moon.… |

Descartados: 463 (no cabe en el presupuesto (173 tokens)); 100 (no cabe en el presupuesto (189 tokens)); 53 (no cabe en el presupuesto (165 tokens)); 164 (no cabe en el presupuesto (164 tokens)); 212 (no cabe en el presupuesto (185 tokens)); 99 (no cabe en el presupuesto (174 tokens))

### Q30 [literal] What lies beneath the icy shell of Europa?

- Respuestas aceptadas: a saltwater ocean, saltwater ocean; fragmentos relevantes: [108, 110, 111]
- Correcciones: ninguna
- **Respuesta: saltwater ocean** · score_difference = 10.25 · fragmento de origen: 111 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 4 fragmentos, 421 tokens de 491 disponibles; entrada al modelo 175/512
- Tiempos: búsqueda 1.9 ms · selección 7.7 ms · modelo 465 ms · total 474 ms
- Exacta (KMP): saltwater ocean (10.25) · correcta y respaldada · fragmentos [111, 138, 113, 183]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 111 ← respuesta | Europa Facts > Facts About Europa | 120 | sí | **Europa** is the fourth largest of Jupiter’s moons. It's the sixth-closest moon to the planet. **Europa** may be one of the most promising places in our solar system to find present-day environments suitable for some form of life beyond Earth. Scientists believe a saltwater ocean **lies** **beneath** its **icy** **shell**, holding twice as much wa… |
| 2 | 138 | Juno Mission > NASA’s Juno Measures Thickness of Europa’s Ice Shell | 164 | no | New insights into Jupiter’s **icy** moon, a candidate in the search for habitable worlds Data from NASA’s Juno mission has provided new insights into the thickness and subsurface structure of the **icy** **shell** encasing Jupiter’s moon **Europa**. Slightly smaller than Earth’s moon, **Europa** is one of the solar system’s highest-priority science… |
| 3 | 113 | Europa Facts > Europa News / Europa Clipper Website | 101 | no | NASA Samples Antarctic Water to Inform Search for Life on **Icy** Worlds Ammonia-Bearing Compounds Discovered at Surface of Jupiter’s Moon **Europa** NASA’s Galileo Mission Points to Ammonia at **Europa**, Recent Study Shows NASA’s Juno Measures Thickness of **Europa’s** Ice **Shell** **Europa** Clipper’s main science goal is to determine whether t… |
| 4 | 183 | Juno Mission > Europa Clipper | 38 | no | Scheduled to reach Jupiter's moon **Europa** in 2030, this NASA mission will search **beneath** **Europa's** **icy** surface for signs of life. Learn More About **Europa** and the Clipper Mission… |

Descartados: 201 (no cabe en el presupuesto (106 tokens)); 101 (no cabe en el presupuesto (183 tokens)); 421 (no cabe en el presupuesto (162 tokens)); 102 (no cabe en el presupuesto (138 tokens)); 93 (no cabe en el presupuesto (198 tokens)); 117 (no cabe en el presupuesto (139 tokens))

### Q35 [literal] How far is the Sun from Earth?

- Respuestas aceptadas: 93 million miles (150 million kilometers), 93 million miles, 150 million kilometers; fragmentos relevantes: [429, 438]
- Correcciones: ninguna
- **Respuesta: 60 times** · score_difference = 1.14 · fragmento de origen: 340 · EM 0, F1 0.00 · **recuperación incompleta**
- Contexto: 4 fragmentos, 427 tokens de 492 disponibles; entrada al modelo 190/512
- Tiempos: búsqueda 5.2 ms · selección 6.6 ms · modelo 459 ms · total 471 ms
- Exacta (KMP): 60 times (1.14) · recuperación incompleta · fragmentos [340, 322, 422, 420]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 340 ← respuesta | New Horizons Mission > Key Dates | 44 | no | Oct. 1, 2024: New Horizons passed 60 times as **far** from the **Sun** as **Earth** is, meaning the spacecraft is twice as **far** out as Pluto was when New Horizons flew by on July 14, 2015.… |
| 2 | 322 | Neptune Facts > Introduction | 133 | no | Dark, cold, and whipped by supersonic winds, ice giant Neptune is more than 30 times as **far** from the **Sun** as **Earth**. Neptune is the only planet in our solar system not visible to the naked eye (Uranus is just barely visible for those with excellent eyesight under dark-sky conditions, provided you know where to look). In 2011 Neptune compl… |
| 3 | 422 | Solar System Facts > Size and Distance | 180 | no | The Oort Cloud is made of icy pieces of space debris - some bigger than mountains – orbiting our **Sun** as **far** as 1.6 light-years away. This shell of material is thick, extending from 5,000 astronomical units to 100,000 astronomical units. One astronomical unit (or AU) is the distance from the **Sun** to **Earth**, or about 93 million miles (1… |
| 4 | 420 | Solar System Facts > Namesake / Potential for Life | 72 | no | Our planetary system is called “the solar system” because we use the word “solar” to describe things related to our star, after the Latin word for **Sun**, "solis." So **far**, we've only know about life on **Earth**, but NASA is searching for life on other worlds in our solar system and beyond.… |

Descartados: 310 (redundante con el fragmento 309 (Jaccard 0.52)); 309 (no cabe en el presupuesto (170 tokens)); 438 (no cabe en el presupuesto (171 tokens)); 393 (no cabe en el presupuesto (182 tokens)); 288 (no cabe en el presupuesto (163 tokens)); 365 (no cabe en el presupuesto (151 tokens))

### Q39 [literal] Who led the committee that selected the contents of the golden record?

- Respuestas aceptadas: Carl Sagan; fragmentos relevantes: [505]
- Correcciones: ninguna
- **Respuesta: Carl Sagan** · score_difference = 9.54 · fragmento de origen: 505 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 6 fragmentos, 475 tokens de 487 disponibles; entrada al modelo 173/512
- Tiempos: búsqueda 1.4 ms · selección 6.5 ms · modelo 576 ms · total 584 ms
- Exacta (KMP): Carl Sagan (9.54) · correcta y respaldada · fragmentos [505, 301, 341, 182, 299, 303]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 505 ← respuesta | Voyager Mission > The Interstellar Mission / The Golden Record | 53 | sí | After completing the first in-depth reconnaissance of the outer planets, the twin Voyagers are on a new mission to chart the edge of interstellar space. The **contents** of the **golden** **record** were **selected** for NASA by a **committee** **led** by Carl Sagan of Cornell University.… |
| 2 | 301 | Planetary Missions > New Frontiers | 130 | no | New Frontiers investigation proposals are solicited via the Announcement of Opportunity (AO) process. Each mission proposal is **led** by a principal investigator (PI) who is typically affiliated with a university or research institution. The PI **selects** team members from industry, small businesses, government laboratories and universities to de… |
| 3 | 341 | New Horizons Mission > In Depth: New Horizons | 158 | no | New Horizons is a NASA mission to study the dwarf planet Pluto, its moons, and other objects in the Kuiper Belt, a region of the solar system that extends from about 30 AU, near the orbit of Neptune, to about 50 AU from the Sun. It was the first mission in NASA’s New Frontiers program, a medium-class, competitively **selected**, and principal inves… |
| 4 | 182 | Juno Mission > Continuing a Legacy | 35 | no | Juno builds on the work of previous missions to Jupiter, and paves the way for missions yet to come. Learn About the Heritage of Discovery That **Led** to Juno… |
| 5 | 299 | Planetary Missions > About Our Flight Programs | 68 | no | We’re overseeing a fleet of missions **led** by NASA and scientists around the world. The missions vary in size, cost and complexity. Our programs also include “missions of opportunity” that enable the U.S. science community to participate in non-NASA missions or to use existing NASA spacecraft for a new mission.… |
| 6 | 303 | Moon Facts > La NASA refuerza Artemis: añade una misión y perfecciona  | 33 | no | Earth's Moon **records** evidence of our solar system's history in the form of impact craters, cooled lava landforms, ancient ice deposits, and more.… |

Descartados: 131 (no cabe en el presupuesto (209 tokens)); 71 (no cabe en el presupuesto (177 tokens)); 228 (no cabe en el presupuesto (79 tokens)); 55 (no cabe en el presupuesto (121 tokens))

### Q43 [paraphrase] Which world circles closest to our star?

- Respuestas aceptadas: Mercury; fragmentos relevantes: [284, 383, 427]
- Correcciones: ninguna
- **Respuesta: Io** · score_difference = 4.21 · fragmento de origen: 196 · EM 0, F1 0.00 · **recuperación incompleta**
- Contexto: 4 fragmentos, 472 tokens de 492 disponibles; entrada al modelo 188/512
- Tiempos: búsqueda 2.1 ms · selección 6.3 ms · modelo 526 ms · total 535 ms
- Exacta (KMP): Io (4.21) · recuperación incompleta · fragmentos [195, 196, 420, 467]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 195 | Juno Mission > Juno's Io Encounters | 178 | no | Io is caught in a tug-of-war between Jupiter's powerful gravity and the smaller pull from two neighboring moons, churning its insides and creating eruptions and lakes of lava that cover its surface. Meanwhile, the gravitational pull Io exerted on Juno during the Feb. 3 flyby has reduced the spacecraft’s orbit around Jupiter to 33 days. It originall… |
| 2 | 196 ← respuesta | Juno Mission > Juno's Io Encounters | 91 | no | Juno's flyby was the **closest** of any spacecraft since the Galileo orbiter's visit two decades earlier, and brought Juno within about 930 miles (1,500 kilometers) of Io, the most volcanic **world** in our solar system. This image was compiled from JunoCam's red, blue, and green filters, from an altitude of 1,764 miles (about 2,840 km), during Jun… |
| 3 | 420 | Solar System Facts > Namesake / Potential for Life | 72 | no | Our planetary system is called “the solar system” because we use the word “solar” to describe things related to our **star**, after the Latin word for Sun, "solis." So far, we've only know about life on Earth, but NASA is searching for life on other **worlds** in our solar system and beyond.… |
| 4 | 467 | Uranus Facts > Introduction | 133 | no | Uranus is a very cold and windy **world**. The ice giant is surrounded by 13 faint rings and 28 small moons. Uranus rotates at a nearly 90-degree angle from the plane of its orbit. This unique tilt makes Uranus appear to spin sideways, orbiting the Sun like a rolling ball. Uranus was the first planet found with the aid of a telescope. It was discov… |

Descartados: 167 (no cabe en el presupuesto (183 tokens)); 116 (no cabe en el presupuesto (162 tokens)); 237 (no cabe en el presupuesto (176 tokens)); 495 (no cabe en el presupuesto (168 tokens)); 247 (no cabe en el presupuesto (161 tokens)); 143 (no cabe en el presupuesto (168 tokens))

### Q45 [paraphrase] What is the tallest volcano on the red planet?

- Respuestas aceptadas: Olympus Mons; fragmentos relevantes: [278]
- Correcciones: ninguna
- **Respuesta: I don't know** · score_difference = 0.00 · fragmento de origen: — · EM 0, F1 0.00 · **recuperación incompleta** · tramo incorrecto (vacío)
- Contexto: 6 fragmentos, 397 tokens de 490 disponibles; entrada al modelo 165/512
- Tiempos: búsqueda 4.2 ms · selección 6.2 ms · modelo 565 ms · total 576 ms
- Exacta (KMP): I don't know (0.00) · recuperación incompleta · fragmentos [276, 267, 273, 377, 265, 255]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 276 | Mars Facts > Surface | 153 | no | The **Red** **Planet** is actually many colors. At the surface, we see colors such as brown, gold, and tan. The reason Mars looks reddish is due to oxidization — or rusting — of iron in the rocks, regolith (Martian “soil”), and dust of Mars. This dust gets kicked up into the atmosphere and from a distance makes the **planet** appear mostly **red**.… |
| 2 | 267 | Mars Facts > Namesake | 84 | no | Mars was named by the ancient Romans for their god of war because its reddish color was reminiscent of blood. Other civilizations also named the **planet** for this attribute — for example, the Egyptians called it "Her Desher," meaning "the **red** one." Even today, it is frequently called the "**Red** **Planet**" because iron minerals in the Marti… |
| 3 | 273 | Mars Facts > Rings | 34 | no | Mars has no rings. However, in 50 million years when Phobos crashes into Mars or breaks apart, it could create a dusty ring around the **Red** **Planet**.… |
| 4 | 377 | Perseverance Mission > The Mars Report | 37 | no | Your source for everything on or about the **Red** **Planet**, continuing NASA's six decades of unparalleled exploration and discoveries — mission news, science findings, unique Mars imagery, and more.… |
| 5 | 265 | Mars Facts > Introduction | 46 | no | Mars — the fourth **planet** from the Sun — is a dusty, cold, desert world with a very thin atmosphere. This dynamic **planet** has seasons, polar ice caps, extinct **volcanoes**, canyons, and weather.… |
| 6 | 255 | Mars Exploration > CURIOSITY MARS ROVER / Active Mission | 45 | no | Curiosity is investigating Mars to determine whether the **Red** **Planet** was ever habitable to microbial life. Launch: Nov. 26, 2011 / 15:02 UTC Mars Landing: Aug. 6, 2012 / 05:32 UTC… |

Descartados: 247 (no cabe en el presupuesto (161 tokens)); 264 (no cabe en el presupuesto (93 tokens)); 400 (no cabe en el presupuesto (189 tokens)); 83 (no cabe en el presupuesto (200 tokens))

### Q47 [paraphrase] What enormous storm rages on the biggest planet?

- Respuestas aceptadas: Great Red Spot; fragmentos relevantes: [200, 211, 212, 213, 214]
- Correcciones: rages -> ranges (OSA d=1, peso 0.83); rages -> ages (OSA d=1, peso 0.80); rages -> rates (OSA d=1, peso 0.80)
- **Respuesta: Great Red Spot** · score_difference = 1.69 · fragmento de origen: 200 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 3 fragmentos, 394 tokens de 490 disponibles; entrada al modelo 185/512
- Tiempos: búsqueda 34.5 ms · selección 6.0 ms · modelo 411 ms · total 451 ms
- Exacta (KMP): Great Red Spot (1.69) · correcta y respaldada · fragmentos [200, 72, 75, 281]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 200 ← respuesta | Jupiter Facts > Introduction / Namesake | 139 | sí | Jupiter's signature stripes and swirls are actually cold, windy clouds of ammonia and water, floating in an atmosphere of hydrogen and helium. The dark orange stripes are called belts, while the lighter bands are called zones, and they flow east and west in opposite directions. Jupiter’s iconic Great Red Spot is a giant **storm** bigger than Earth … |
| 2 | 417 | Saturn Facts > Magnetosphere | 173 | no | Saturn's magnetic field is smaller than Jupiter's but still 578 times as powerful as Earth's. Saturn, the rings, and many of the satellites lie totally within Saturn's **enormous** magnetosphere, the region of space in which the behavior of electrically charged particles is influenced more by Saturn's magnetic field than by the solar wind. Aurorae … |
| 3 | 281 | Mars Facts > Atmosphere | 84 | no | If you were to stand on the surface of Mars on the equator at noon, it would feel like spring at your feet (75 degrees Fahrenheit or 24 degrees Celsius) and winter at your head (32 degrees Fahrenheit or 0 degrees Celsius). Occasionally, winds on Mars are strong enough to create dust **storms** that cover much of the **planet**. After such **storms*… |

Descartados: 430 (no cabe en el presupuesto (174 tokens)); 434 (no cabe en el presupuesto (166 tokens)); 352 (no cabe en el presupuesto (190 tokens)); 72 (no cabe en el presupuesto (128 tokens)); 83 (no cabe en el presupuesto (200 tokens)); 75 (no cabe en el presupuesto (112 tokens)); 137 (no cabe en el presupuesto (155 tokens))

### Q49 [paraphrase] Which moon of the ringed planet has seas of hydrocarbons?

- Respuestas aceptadas: Titan; fragmentos relevantes: [457]
- Correcciones: ringed -> ranged (OSA d=1, peso 0.83); ringed -> hinged (OSA d=1, peso 0.83)
- **Respuesta: Titan** · score_difference = 0.71 · fragmento de origen: 457 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 3 fragmentos, 429 tokens de 486 disponibles; entrada al modelo 189/512
- Tiempos: búsqueda 8.7 ms · selección 6.3 ms · modelo 455 ms · total 470 ms
- Exacta (KMP): Titan (0.71) · correcta y respaldada · fragmentos [457, 409, 205, 43, 403]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 457 ← respuesta | Titan Facts > Facts About Titan | 91 | sí | Titan is the target of NASA's upcoming Dragonfly mission. Titan is Saturn's largest **moon**, and the only **moon** in our solar system known to have a substantial atmosphere. Titan is the only place besides Earth known to have liquids on its surface. It has clouds, rain, rivers, lakes and **seas** of liquid **hydrocarbons** like methane and ethane… |
| 2 | 314 | Moon Facts > Surface | 167 | no | With too sparse an atmosphere to impede impacts, a steady rain of asteroids, meteoroids, and comets strikes the surface of the **Moon**, leaving numerous craters behind. Tycho Crater is more than 52 miles (85 kilometers) wide. Over billions of years, these impacts have ground up the surface of the **Moon** into fragments **ranging** from huge bould… |
| 3 | 328 | Neptune Facts > Moons | 173 | no | Neptune has 16 known **moons**. Neptune's largest **moon** Triton was discovered on Oct. 10, 1846, by William Lassell, just 17 days after Johann Gottfried Galle discovered the **planet**. Since Neptune was named for the Roman god of the **sea**, its **moons** are named for various lesser **sea** gods and nymphs in Greek mythology. Triton is the onl… |

Descartados: 480 (no cabe en el presupuesto (140 tokens)); 409 (no cabe en el presupuesto (158 tokens)); 491 (no cabe en el presupuesto (171 tokens)); 18 (no cabe en el presupuesto (181 tokens)); 315 (no cabe en el presupuesto (185 tokens)); 148 (no cabe en el presupuesto (202 tokens)); 501 (no cabe en el presupuesto (124 tokens))

### Q01-T [typo] When was Pluot discovered?

- Pregunta original (sin errores): When was Pluto discovered?
- Respuestas aceptadas: 1930; fragmentos relevantes: [386, 389]
- Correcciones: pluot -> pluto (OSA d=1, peso 0.80)
- **Respuesta: 1930** · score_difference = 8.46 · fragmento de origen: 240 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 3 fragmentos, 380 tokens de 493 disponibles; entrada al modelo 182/512
- Tiempos: búsqueda 2.7 ms · selección 2.4 ms · modelo 497 ms · total 502 ms
- Exacta (KMP): I don't know (0.00) · recuperación incompleta · fragmentos [461, 329, 404, 411, 306, 129]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 240 ← respuesta | Kuiper Belt Facts > Pluto's Place in the Kuiper Belt | 173 | no | In 1930, **Pluto** became the first Kuiper Belt object to be **discovered**. It was found at a time before astronomers had reason to expect a large population of icy worlds beyond Neptune. Today it's known as the "King of the Kuiper Belt" – and it's the largest object in the region, even though another object similar in size, called Eris, has a sli… |
| 2 | 389 | Pluto Facts > Namesake | 156 | sí | In 1930, Venetia Burney of Oxford, England, suggested to her grandfather that the new discovery be named for the Roman god of the underworld. He forwarded the name to the Lowell Observatory and it was selected. In an interview with NASA in January 2006, Venetia said she offered the name **Pluto** over breakfast with her mother and grandfather. It w… |
| 3 | 461 | Triton Facts > Contents / Discovery | 53 | no | Global color mosaic of Triton, taken in 1989 by Voyager 2 during its flyby of the Neptune system. Triton was **discovered** on Oct. 10, 1846 by British astronomer William Lassell, just 17 days after Neptune itself was **discovered**.… |

Descartados: 386 (no cabe en el presupuesto (184 tokens)); 47 (no cabe en el presupuesto (156 tokens)); 395 (no cabe en el presupuesto (188 tokens)); 396 (no cabe en el presupuesto (181 tokens)); 392 (no cabe en el presupuesto (147 tokens)); 390 (no cabe en el presupuesto (168 tokens)); 388 (no cabe en el presupuesto (143 tokens))

### Q10-T [typo] What is the Graet Red Spot?

- Pregunta original (sin errores): What is the Great Red Spot?
- Respuestas aceptadas: a giant storm bigger than Earth, giant storm; fragmentos relevantes: [200, 211, 212, 213, 214]
- Correcciones: graet -> great (OSA d=1, peso 0.80); graet -> grant (OSA d=1, peso 0.80)
- **Respuesta: I don't know** · score_difference = 0.00 · fragmento de origen: — · EM 0, F1 0.00 · **falla del modelo** · tramo incorrecto (vacío)
- Contexto: 3 fragmentos, 465 tokens de 492 disponibles; entrada al modelo 188/512
- Tiempos: búsqueda 3.4 ms · selección 7.3 ms · modelo 537 ms · total 547 ms
- Exacta (KMP): I don't know (0.00) · falla del modelo · fragmentos [213, 211, 175]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 213 | Jupiter Facts > Atmosphere | 178 | sí | The findings also indicate these storms are far taller than expected, with some extending 60 miles (100 kilometers) below the cloud tops and others, including the **Great** **Red** **Spot**, extending over 200 miles (350 kilometers). This surprising discovery demonstrates that the vortices cover regions beyond those where water condenses and clouds… |
| 2 | 211 | Jupiter Facts > Atmosphere | 163 | sí | Jupiter's fast rotation – spinning once every 10 hours – creates strong jet streams, separating its clouds into dark belts and bright zones across long stretches. With no solid surface to slow them down, Jupiter's **spots** can persist for many years. Stormy Jupiter is swept by over a dozen prevailing winds, some reaching up to 335 miles per hour (… |
| 3 | 175 | Juno Mission > Scientific Discoveries and Results | 126 | no | The closest images of Io came from Juno’s passes in December 2023 and February 2024, but the monitoring will continue through the current end of the extended mission, scheduled in September 2025. Juno has spent years tracking the **Great** Blue **Spot**. Not to be confused with Jupiter’s iconic **red** storm, the Blue **Spot** is an invisible, loca… |

Descartados: 212 (no cabe en el presupuesto (185 tokens)); 174 (no cabe en el presupuesto (186 tokens)); 200 (no cabe en el presupuesto (139 tokens)); 173 (no cabe en el presupuesto (182 tokens)); 214 (no cabe en el presupuesto (165 tokens)); 247 (no cabe en el presupuesto (161 tokens)); 335 (no cabe en el presupuesto (141 tokens))

### Q17-T [typo] When was Neptue discovered?

- Pregunta original (sin errores): When was Neptune discovered?
- Respuestas aceptadas: 1846; fragmentos relevantes: [322, 323, 328, 461]
- Correcciones: neptue -> neptune (OSA d=1, peso 0.86)
- **Respuesta: 1846** · score_difference = 5.44 · fragmento de origen: 323 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 4 fragmentos, 396 tokens de 494 disponibles; entrada al modelo 181/512
- Tiempos: búsqueda 3.9 ms · selección 4.6 ms · modelo 465 ms · total 473 ms
- Exacta (KMP): I don't know (0.00) · falla del modelo · fragmentos [461, 329, 404, 411, 306, 129]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 461 | Triton Facts > Contents / Discovery | 53 | sí | Global color mosaic of Triton, taken in 1989 by Voyager 2 during its flyby of the **Neptune** system. Triton was **discovered** on Oct. 10, 1846 by British astronomer William Lassell, just 17 days after **Neptune** itself was **discovered**.… |
| 2 | 328 | Neptune Facts > Moons | 173 | sí | **Neptune** has 16 known moons. **Neptune's** largest moon Triton was **discovered** on Oct. 10, 1846, by William Lassell, just 17 days after Johann Gottfried Galle **discovered** the planet. Since **Neptune** was named for the Roman god of the sea, its moons are named for various lesser sea gods and nymphs in Greek mythology. Triton is the only la… |
| 3 | 323 ← respuesta | Neptune Facts > Discovery and Namesake | 142 | sí | Galileo recorded **Neptune** as a fixed star during observations with his small telescope in 1612 and 1613. More than 200 years later, the ice giant became the first planet located through mathematical predictions rather than through regular observations of the sky. Because Uranus didn't travel exactly as astronomers expected it to, French mathemat… |
| 4 | 321 | Neptune Facts > Our Solar System | 30 | no | **Neptune** is the eighth and most distant planet in our solar system. Sometimes **Neptune** is even farther from the Sun than dwarf planet Pluto.… |

Descartados: 240 (no cabe en el presupuesto (173 tokens)); 227 (no cabe en el presupuesto (170 tokens)); 386 (no cabe en el presupuesto (184 tokens)); 326 (no cabe en el presupuesto (186 tokens)); 325 (no cabe en el presupuesto (110 tokens)); 322 (no cabe en el presupuesto (133 tokens))

### Q25-T [typo] What are Saturn's rinngs made of?

- Pregunta original (sin errores): What are Saturn's rings made of?
- Respuestas aceptadas: billions of small chunks of ice and rock, ice and rock; fragmentos relevantes: [409]
- Correcciones: rinngs -> rings (Jaccard 0.86 con ngram2)
- **Respuesta: billions of small chunks of ice and rock** · score_difference = 11.76 · fragmento de origen: 409 · EM 1, F1 1.00 · **correcta y respaldada**
- Contexto: 4 fragmentos, 453 tokens de 489 disponibles; entrada al modelo 171/512
- Tiempos: búsqueda 5.2 ms · selección 3.9 ms · modelo 554 ms · total 563 ms
- Exacta (KMP): hydrogen and helium (6.98) · recuperación incompleta · fragmentos [403, 412, 413, 103, 407]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 409 ← respuesta | Saturn Facts > Rings | 158 | sí | **Saturn's** **rings** are thought to be pieces of comets, asteroids, or shattered moons that broke up before they reached the planet, torn apart by **Saturn's** powerful gravity. They are **made** of billions of small chunks of ice and rock coated with other materials such as dust. The **ring** particles mostly range from tiny, dust-sized icy grai… |
| 2 | 403 | Saturn Facts > Introduction | 90 | no | Like fellow gas giant Jupiter, **Saturn** is a massive ball **made** mostly of hydrogen and helium. **Saturn** is not the only planet to have **rings**, but none are as spectacular or as complex as **Saturn's**. **Saturn** also has dozens of moons. From the jets of water that spray from **Saturn's** moon Enceladus to the methane lakes on smoggy Tit… |
| 3 | 102 | Enceladus Facts > Overview / Discovery | 138 | no | The E **ring** is mostly **made** of ice droplets, but among them are peculiar nanograins of silica, which can only be generated where liquid water and rock interact at temperatures above about 200 degrees Fahrenheit (90 degrees Celsius). This, among other evidence, points to hydrothermal vents deep beneath Enceladus’ icy shell, not unlike the hydr… |
| 4 | 40 | Cassini Mission > Mission to Saturn | 69 | no | For more than a decade, NASA’s Cassini spacecraft shared the wonders of **Saturn**, its spectacular **rings**, and its family of icy moons. Cassini was a sophisticated robotic spacecraft sent to study **Saturn** and its complex system of **rings** and moons in unprecedented detail. It was one of the most ambitious efforts ever mounted in planetary … |

Descartados: 411 (redundante con el fragmento 410 (Jaccard 0.54)); 101 (no cabe en el presupuesto (183 tokens)); 410 (no cabe en el presupuesto (191 tokens)); 473 (no cabe en el presupuesto (117 tokens)); 417 (no cabe en el presupuesto (173 tokens)); 41 (no cabe en el presupuesto (103 tokens))

### Q35-T [typo] How far is the Sun from Earht?

- Pregunta original (sin errores): How far is the Sun from Earth?
- Respuestas aceptadas: 93 million miles (150 million kilometers), 93 million miles, 150 million kilometers; fragmentos relevantes: [429, 438]
- Correcciones: earht -> earth (OSA d=1, peso 0.80)
- **Respuesta: I don't know** · score_difference = 0.00 · fragmento de origen: — · EM 0, F1 0.00 · **recuperación incompleta** · tramo incorrecto (vacío)
- Contexto: 4 fragmentos, 427 tokens de 491 disponibles; entrada al modelo 191/512
- Tiempos: búsqueda 5.1 ms · selección 1.8 ms · modelo 495 ms · total 502 ms
- Exacta (KMP): I don't know (0.00) · recuperación incompleta · fragmentos [340, 322, 365, 420]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 340 | New Horizons Mission > Key Dates | 44 | no | Oct. 1, 2024: New Horizons passed 60 times as **far** from the **Sun** as **Earth** is, meaning the spacecraft is twice as **far** out as Pluto was when New Horizons flew by on July 14, 2015.… |
| 2 | 322 | Neptune Facts > Introduction | 133 | no | Dark, cold, and whipped by supersonic winds, ice giant Neptune is more than 30 times as **far** from the **Sun** as **Earth**. Neptune is the only planet in our solar system not visible to the naked eye (Uranus is just barely visible for those with excellent eyesight under dark-sky conditions, provided you know where to look). In 2011 Neptune compl… |
| 3 | 422 | Solar System Facts > Size and Distance | 180 | no | The Oort Cloud is made of icy pieces of space debris - some bigger than mountains – orbiting our **Sun** as **far** as 1.6 light-years away. This shell of material is thick, extending from 5,000 astronomical units to 100,000 astronomical units. One astronomical unit (or AU) is the distance from the **Sun** to **Earth**, or about 93 million miles (1… |
| 4 | 420 | Solar System Facts > Namesake / Potential for Life | 72 | no | Our planetary system is called “the solar system” because we use the word “solar” to describe things related to our star, after the Latin word for **Sun**, "solis." So **far**, we've only know about life on **Earth**, but NASA is searching for life on other worlds in our solar system and beyond.… |

Descartados: 310 (redundante con el fragmento 309 (Jaccard 0.52)); 309 (no cabe en el presupuesto (170 tokens)); 438 (no cabe en el presupuesto (171 tokens)); 393 (no cabe en el presupuesto (182 tokens)); 288 (no cabe en el presupuesto (163 tokens)); 365 (no cabe en el presupuesto (151 tokens))

### Q42-T [typo] Where do comeos come from?

- Pregunta original (sin errores): Where do comets come from?
- Respuestas aceptadas: the Kuiper Belt and the Oort Cloud, Kuiper Belt, Oort Cloud; fragmentos relevantes: [59, 60, 220, 222, 225, 226, 245, 359, 360, 361, 362, 363, 364, 365, 366, 367, 368]
- Correcciones: comeos -> comets (OSA d=1, peso 0.83); comeos -> comes (OSA d=1, peso 0.83)
- **Respuesta: I don't know** · score_difference = 0.00 · fragmento de origen: — · EM 0, F1 0.00 · **falla del modelo** · tramo incorrecto (vacío)
- Contexto: 6 fragmentos, 470 tokens de 493 disponibles; entrada al modelo 138/512
- Tiempos: búsqueda 4.2 ms · selección 7.1 ms · modelo 630 ms · total 642 ms
- Exacta (KMP): I don't know (0.00) · falla del modelo · fragmentos [182, 251, 359, 85, 128, 426]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 359 | Oort Cloud Facts > La NASA refuerza Artemis: añade una misión y perfec | 60 | sí | In 1950, astronomer Jan Oort proposed that some **comets** **come** from a vast, extremely distant spherical shell of icy bodies surrounding the solar system. This giant swarm of objects, now named the Oort Cloud, occupies space at a distance between 5,000 and 100,000 astronomical units.… |
| 2 | 245 | Kuiper Belt Facts > Relationship to Comets | 129 | sí | Given their frequent trips into the inner solar system, most tend to exhaust their volatile ices fairly quickly and eventually become dormant, or dead, **comets** with little or no detectable activity. Researchers have found that some near-Earth asteroids are actually burned-out **comets**, and most of them would have started out in the Kuiper Belt… |
| 3 | 426 | Solar System Facts > Formation | 93 | no | These clumps smashed into one another, forming larger and larger objects. Some of them grew big enough for their gravity to shape them into spheres, becoming planets, dwarf planets, and large moons. In other cases, planets did not form: the asteroid belt is made of bits and pieces of the early solar system that could never quite **come** together i… |
| 4 | 182 | Juno Mission > Continuing a Legacy | 35 | no | Juno builds on the work of previous missions to Jupiter, and paves the way for missions yet to **come**. Learn About the Heritage of Discovery That Led to Juno… |
| 5 | 251 | Mars Exploration > ‘Green for Touchdown,’ on the Red Planet | 50 | no | Video celebrating the 50th anniversary of the Viking 1 landing on Mars, the era of Martian surface exploration that it began, and the missions and discoveries ever since, and those yet to **come**. Includes historic footage and commentary from Viking team members.… |
| 6 | 232 | Kuiper Belt Facts > Classical KBOs | 105 | no | The cold classical KBOs have orbits that never **come** very close to Neptune, and thus they remain "cool" and unperturbed by the giant planet's gravity. Their orbits likely haven't moved much for billions of years. In contrast, the hot classical KBOs have had interactions with Neptune in the past (that is, with the giant planet's gravity). These i… |

Descartados: 367 (no cabe en el presupuesto (142 tokens)); 37 (no cabe en el presupuesto (216 tokens)); 237 (no cabe en el presupuesto (176 tokens)); 401 (no cabe en el presupuesto (177 tokens))

### Q51 [no_answer] How many people live on Mars today?

- Respuestas aceptadas: (ninguna: no está en la colección); fragmentos relevantes: —
- Correcciones: ninguna
- **Respuesta: I don't know** · score_difference = 0.00 · fragmento de origen: — · EM 1, F1 1.00 · **no-respuesta correcta**
- Contexto: 6 fragmentos, 485 tokens de 492 disponibles; entrada al modelo 177/512
- Tiempos: búsqueda 2.4 ms · selección 7.7 ms · modelo 776 ms · total 786 ms
- Exacta (KMP): I don't know (0.00) · no-respuesta correcta · fragmentos [26, 48, 268, 248, 282, 267]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 26 | Asteroid Facts > Large Asteroids Have Hit Earth in the Past | 167 | no | A house-sized asteroid exploded over Chelyabinsk, Russia, on Feb.15, 2013. The explosion released the energy equivalent to about 440,000 tons of TNT, generating a shock wave that damaged some buildings and blew out windows across 200 square miles. Hundreds of **people** were injured in the blast, mostly due to the broken glass. Another impact site,… |
| 2 | 48 | Ceres Facts > Potential for Life | 112 | no | Ceres is one of the few places in our solar system where scientists would like to search for possible signs of life. Ceres has something a lot of other planets don't: water. Here on Earth, water is essential for life, so it's possible someplace else with that ingredient and a few other conditions could support life, as well. If anything does **live… |
| 3 | 268 | Mars Facts > Potential for Life | 38 | no | Scientists don't expect to find **living** things currently thriving on **Mars**. Instead, they're looking for signs of life that existed long ago, when **Mars** was warmer and covered with water.… |
| 4 | 248 | Mars Exploration > Perseverance, On a Roll | 49 | no | Watch an animated map of the rover's path — from 2021 landing to record-setting milestone — see the runner-up rovers, on **Mars** or the Moon, and learn more about how Perseverance got where it is **today**.… |
| 5 | 282 | Mars Facts > Magnetosphere | 37 | no | **Mars** has no global magnetic field **today**, but areas of the Martian crust in the southern hemisphere are highly magnetized, indicating traces of a magnetic field from 4 billion years ago.… |
| 6 | 267 | Mars Facts > Namesake | 84 | no | **Mars** was named by the ancient Romans for their god of war because its reddish color was reminiscent of blood. Other civilizations also named the planet for this attribute — for example, the Egyptians called it "Her Desher," meaning "the red one." Even **today**, it is frequently called the "Red Planet" because iron minerals in the Martian dirt … |

Descartados: 279 (no cabe en el presupuesto (132 tokens)); 283 (no cabe en el presupuesto (105 tokens)); 250 (no cabe en el presupuesto (122 tokens)); 375 (no cabe en el presupuesto (183 tokens))

### Q53 [no_answer] How much does a ticket to the Moon cost?

- Respuestas aceptadas: (ninguna: no está en la colección); fragmentos relevantes: —
- Correcciones: ticket -> tick (Jaccard 0.50 con ngram2)
- **Respuesta: I don't know** · score_difference = 0.00 · fragmento de origen: — · EM 1, F1 1.00 · **no-respuesta correcta**
- Contexto: 5 fragmentos, 487 tokens de 490 disponibles; entrada al modelo 147/512
- Tiempos: búsqueda 6.1 ms · selección 5.7 ms · modelo 723 ms · total 735 ms
- Exacta (KMP): I don't know (0.00) · no-respuesta correcta · fragmentos [301, 299, 300, 306, 307]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 301 | Planetary Missions > New Frontiers | 130 | no | New Frontiers investigation proposals are solicited via the Announcement of Opportunity (AO) process. Each mission proposal is led by a principal investigator (PI) who is typically affiliated with a university or research institution. The PI selects team members from industry, small businesses, government laboratories and universities to develop th… |
| 2 | 299 | Planetary Missions > About Our Flight Programs | 68 | no | We’re overseeing a fleet of missions led by NASA and scientists around the world. The missions vary in size, **cost** and complexity. Our programs also include “missions of opportunity” that enable the U.S. science community to participate in non-NASA missions or to use existing NASA spacecraft for a new mission.… |
| 3 | 300 | Planetary Missions > Discovery | 135 | no | The goal of NASA’s Discovery Program is to provide frequent flight opportunities for high-quality, high-value, focused, planetary science investigations that can be accomplished under a not-to-exceed **cost** cap. By conducting a series of planetary science investigations, NASA will provide a mechanism by which pressing questions in planetary scien… |
| 4 | 306 | Moon Facts > How the Moon Got Its Name | 55 | no | Our **Moon** shares a name with all **moons** simply because people didn't know other **moons** existed until Galileo Galilei discovered four **moons** orbiting Jupiter in 1610. In Latin, the **Moon** was called Luna, which is the main adjective for all things **Moon**-related: lunar.… |
| 5 | 310 | Moon Facts > Orbit and Rotation / Moons | 101 | no | And a "new **moon**" occurs when the far side of the **Moon** has full sunlight, and the side facing us is having its night. The **Moon** makes a complete orbit around Earth in 27 Earth days and rotates or spins at that same rate, or in that same amount of time. Because Earth is moving as well – rotating on its axis as it orbits the Sun – from our … |

Descartados: 309 (redundante con el fragmento 310 (Jaccard 0.52)); 500 (no cabe en el presupuesto (190 tokens)); 424 (no cabe en el presupuesto (134 tokens)); 79 (no cabe en el presupuesto (146 tokens)); 308 (no cabe en el presupuesto (103 tokens))

### Q54 [no_answer] Who is the current president of Jupiter?

- Respuestas aceptadas: (ninguna: no está en la colección); fragmentos relevantes: —
- Correcciones: ninguna
- **Respuesta: I don't know** · score_difference = 0.00 · fragmento de origen: — · EM 1, F1 1.00 · **no-respuesta correcta**
- Contexto: 4 fragmentos, 407 tokens de 492 disponibles; entrada al modelo 136/512
- Tiempos: búsqueda 2.9 ms · selección 7.6 ms · modelo 587 ms · total 598 ms
- Exacta (KMP): I don't know (0.00) · no-respuesta correcta · fragmentos [175, 128, 51, 412]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 175 | Juno Mission > Scientific Discoveries and Results | 126 | no | The closest images of Io came from Juno’s passes in December 2023 and February 2024, but the monitoring will continue through the **current** end of the extended mission, scheduled in September 2025. Juno has spent years tracking the Great Blue Spot. Not to be confused with **Jupiter’s** iconic red storm, the Blue Spot is an invisible, localized, i… |
| 2 | 128 | Io Facts > Exploring Io | 95 | no | Most of what we know about Io comes from the Galileo spacecraft, which made a detailed study of the **Jupiter** system. It was Voyager 1 that spotted the first signs of the little moon’s powerful volcanism in 1979. Since 2003, three spacecraft – Ulysses, Cassini, New Horizons, and Juno – have made additional close observations of Io. Juno is **curr… |
| 3 | 51 | Ceres Facts > Formation | 102 | no | Ceres formed along with the rest of the solar system about 4.5 billion years ago when gravity pulled swirling gas and dust in to become a small dwarf planet. Scientists describe Ceres as an "embryonic planet," which means it started to form but didn't quite finish. Nearby **Jupiter's** strong gravity prevented it from becoming a fully formed planet… |
| 4 | 412 | Saturn Facts > Formation | 86 | no | Saturn took shape when the rest of the solar system formed about 4.5 billion years ago when gravity pulled swirling gas and dust in to become this gas giant. About 4 billion years ago, Saturn settled into its **current** position in the outer solar system, where it is the sixth planet from the Sun. Like **Jupiter**, Saturn is mostly made of hydroge… |

Descartados: 206 (no cabe en el presupuesto (117 tokens)); 146 (no cabe en el presupuesto (209 tokens)); 207 (no cabe en el presupuesto (145 tokens)); 147 (no cabe en el presupuesto (187 tokens)); 106 (no cabe en el presupuesto (159 tokens)); 208 (no cabe en el presupuesto (176 tokens))

### Q55 [no_answer] What is the favorite food of astronauts on Pluto?

- Respuestas aceptadas: (ninguna: no está en la colección); fragmentos relevantes: —
- Correcciones: food -> good (OSA d=1, peso 0.75); food -> fold (OSA d=1, peso 0.75); food -> foot (OSA d=1, peso 0.75)
- **Respuesta: I don't know** · score_difference = 0.00 · fragmento de origen: — · EM 1, F1 1.00 · **no-respuesta correcta**
- Contexto: 5 fragmentos, 418 tokens de 490 disponibles; entrada al modelo 102/512
- Tiempos: búsqueda 4.5 ms · selección 6.3 ms · modelo 731 ms · total 742 ms
- Exacta (KMP): I don't know (0.00) · no-respuesta correcta · fragmentos [122, 9, 316, 305]

| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |
|---|---|---|---:|---|---|
| 1 | 358 | New Horizons Mission > New Horizons Stories | 90 | no | NASA’s New Horizons Finds Evidence of Recent Liquid on **Pluto’s** Surface NASA’s New Horizons Spacecraft Wakes from Hibernation in **Good** Health NASA’s New Horizons Enters Mission’s Longest Hibernation Period 10 Years Ago: NASA’s New Horizons Captures **Pluto’s** Heart NASA’s New Horizons Detects Dusty Hints of Extended Kuiper Belt… |
| 2 | 122 | Hubble Space Telescope > What Did Hubble See on Your Birthday? / What  | 71 | no | To celebrate the nation's 250th birthday, NASA expanded this web app with more images! See what Hubble observed on your birthday, or other special occasion, pick your **favorite** images, and share them with friends! See the area of sky Hubble is investigating. Play this trivia game and test your knowledge! Take a virtual tour of Hubble's operation… |
| 3 | 103 | Enceladus Facts > How Enceladus Got Its Name | 89 | no | Enceladus is named after the giant, Enceladus, of Greek mythology. William Herschel's son John Herschel suggested the name in his 1847 publication Results of Astronomical Observation made at the Cape of **Good** Hope, in which he suggested names for the first seven Saturnian moons discovered. He chose these names in particular because Saturn, known… |
| 4 | 316 | Moon Facts > Surface | 85 | no | While you were there, you'd notice that the gravity on the surface of the Moon is one-sixth of Earth's, which is why in footage of moonwalks, **astronauts** appear to almost bounce across the surface. The temperature on the Moon reaches about 260 degrees Fahrenheit (127 degrees Celsius) when in full Sun, but in darkness, the temperatures plummet to… |
| 5 | 305 | Moon Facts > 10 things | 85 | no | It is not breathable. More than 105 robotic spacecraft have been launched to explore the Moon. It is the only celestial body beyond Earth – so far – visited by human beings. The Moon's weak atmosphere and its lack of liquid water cannot support life as we know it. Apollo **astronauts** brought back a total of 842 pounds (382 kilograms) of lunar roc… |

Descartados: 9 (no cabe en el presupuesto (139 tokens)); 315 (no cabe en el presupuesto (185 tokens)); 10 (no cabe en el presupuesto (175 tokens)); 395 (no cabe en el presupuesto (188 tokens)); 396 (no cabe en el presupuesto (181 tokens))

## Casos comentados (datos)

**correcta y respaldada** · Q01 (aproximada)
- Pregunta: When was Pluto discovered? · esperada: 1930 · respuesta: 1930 (score_difference 8.88)
- Relevantes: [386, 389] · recuperados (top-10): [240, 386, 389, 47, 395, 396, 392, 390, 388, 393] · en el contexto: [240, 389, 47] · relevantes en el contexto: [389]
- Fragmento de origen de la respuesta: 240

**recuperación incompleta** · Q09 (aproximada)
- Pregunta: How long is a year on Mars? · esperada: 687 Earth days, 669.6 sols · respuesta: I don't know (score_difference 0.00)
- Relevantes: [270] · recuperados (top-10): [327, 279, 368, 270, 256, 268, 271, 252, 369, 67] · en el contexto: [327, 279, 256, 268, 252, 369, 67] · relevantes en el contexto: ninguno
- Fragmento de origen de la respuesta: —

**falla del modelo** · Q10-T (aproximada)
- Pregunta: What is the Graet Red Spot? · esperada: a giant storm bigger than Earth, giant storm · respuesta: I don't know (score_difference 0.00)
- Relevantes: [200, 211, 212, 213, 214] · recuperados (top-10): [213, 211, 212, 174, 200, 173, 214, 175, 247, 335] · en el contexto: [213, 211, 175] · relevantes en el contexto: [213, 211]
- Fragmento de origen de la respuesta: —

**no-respuesta correcta** · Q51 (aproximada)
- Pregunta: How many people live on Mars today? · esperada: — · respuesta: I don't know (score_difference 0.00)
- Relevantes: — · recuperados (top-10): [26, 279, 48, 268, 248, 282, 283, 267, 250, 375] · en el contexto: [26, 48, 268, 248, 282, 267] · relevantes en el contexto: ninguno
- Fragmento de origen de la respuesta: —

