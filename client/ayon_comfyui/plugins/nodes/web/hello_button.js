app.registerExtension({
    name: "HelloWorldButton",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "HelloWorldButton") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (origOnNodeCreated) origOnNodeCreated.apply(this);

            const btn = document.createElement("button");
            btn.innerText = "Click Me!";
            btn.style.marginTop = "8px";
            btn.onclick = () => {
                console.log("Hello world");
                alert("Hello world from ComfyUI!");
            };

            this.addWidget("custom", "Hello Button", "", () => {}, {element: btn});
        };
    },
});
